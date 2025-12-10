#
# Copyright (C) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import gzip
import json
import os
import random
from logging import getLogger
from typing import List, Union

import boto3
from backend import config
from backend.models.profiles_models import AgentData, ProfileResponse
from backend.utils.profiles_utils import GzipRoute, get_profile_file_name
from botocore.config import Config
from cmp_version import VersionString
from fastapi import APIRouter, Header, HTTPException, Request
from gprofiler_dev import get_s3_profile_dal
from gprofiler_dev.api_key import get_service_by_api_key
from gprofiler_dev.client_handler import ClientHandler 
from gprofiler_dev.postgres.db_manager import DBManager
from gprofiler_dev.postgres.schemas import AgentMetadata, GetServiceResponse
from gprofiler_dev.profiles_utils import get_gprofiler_metadata_utils, get_gprofiler_utils
from gprofiler_dev.tags import CONTAINER_KEY, HOSTNAME_KEY, K8S_OBJ_KEY, container_and_k8s_name

SQS_CONFIG = Config(region_name=config.AWS_DEFAULT_REGION)
GPID_SUPPORT_VERSION = VersionString("1.2.3")

logger = getLogger(__name__)
router = APIRouter()

# handle all the gzip stuff, including length check and parsing
router.route_class = GzipRoute


@router.post("", response_model=ProfileResponse)
def new_profile_v2(
    request: Request,
    agent_data: AgentData,
    gprofiler_api_key: str = Header(...),
    gprofiler_service_name: str = Header(...),
):
    hostname = "unknown"
    
    try:
        service_name, token_id = get_service_by_api_key(gprofiler_api_key, gprofiler_service_name)
        if not service_name:
            raise HTTPException(400, {"message": f"Invalid {config.GPROFILER_SERVICE_NAME} header"})

        db_manager = DBManager()
        gprofiler_utils = get_gprofiler_utils(db_manager)

        profile_dal = get_s3_profile_dal(logger)

        tags: List[str] = []
        gpid = 0

        profile = agent_data.profile

        try:
            line_end_index = profile.find("\n")
            first_line = profile if line_end_index == -1 else profile[:line_end_index]
            assert first_line[0] == "#"

            raw_profile_header = first_line[1:]
            try:
                profile_header = json.loads(raw_profile_header)
            except ValueError:
                logger.error(f"Metadata is not a valid JSON - {raw_profile_header!r}")
                raise
            containers = profile_header.get("containers", [])
            service_env_type = "containers" if containers else "instances"
            for raw_container_name in containers:
                if "ecs-" in raw_container_name:
                    service_env_type = "ecs"
                else:
                    container_name, k8s_obj_name = container_and_k8s_name(raw_container_name)
                    tags.append(f"{CONTAINER_KEY}:{container_name}")
                    if k8s_obj_name:
                        service_env_type = "k8s"
                        tags.append(f"{K8S_OBJ_KEY}:{k8s_obj_name}")
            if "metadata" in profile_header:
                try:
                    metadata = profile_header["metadata"]
                    hostname = metadata["hostname"]
                    metadata["public_ip"] = request.headers.get(
                        "x-forwarded-for", request.client.host if request.client else ""
                    )
                    if "cloud_info" in metadata:
                        metadata["instance_type"] = metadata["cloud_info"].get("instance_type", "")
                    else:
                        metadata["instance_type"] = ""
                    agent_metadata = AgentMetadata(**metadata)

                    agent_version = VersionString(agent_metadata.agent_version)
                    if agent_version >= GPID_SUPPORT_VERSION:
                        metadata_utils = get_gprofiler_metadata_utils(db_manager)

                        if agent_data.gpid is None:
                            raise HTTPException(400, {"message": "gpid must be a part of a json body"})
                        gprofiler_process_id = None
                        if agent_data.gpid:
                            try:
                                gprofiler_process_id = int(agent_data.gpid)
                            except AssertionError as e:
                                logger.error(f"Bad gpid, got the following error: {e}, generating new gpid")

                        if gprofiler_process_id:
                            metadata_utils.processes_queue.put(gprofiler_process_id)
                            service_id = db_manager.get_service_by_profiler_process_id(gprofiler_process_id)
                            service_response = GetServiceResponse(
                                service_id=service_id,
                                does_service_exist=True,
                                profiler_process_id=gprofiler_process_id,
                            )
                            gpid = gprofiler_process_id
                        else:
                            service_response = db_manager.add_service_data(
                                service_name, agent_metadata, extra_cache=False, service_env_type=service_env_type
                            )
                            gpid = service_response.profiler_process_id
                    else:
                        service_response = db_manager.add_service_data(
                            service_name,
                            agent_metadata,
                            extra_cache=True,
                            service_env_type=service_env_type,
                        )
                except Exception as exception:
                    logger.exception(exception)
                    raise
            else:
                error_msg = "Agent metadata is missing, probably you are using and old agent"
                raise HTTPException(400, {"message": error_msg})

            tags.append(f"{HOSTNAME_KEY}:{hostname}")
        except Exception as e:
            exception_msg = "Failed to parse v2 metadata"
            logger.exception(exception_msg)
            raise HTTPException(400, {"message": exception_msg})

        service_id = service_response.service_id
        client_handler = ClientHandler(service_name, service_id, profile_dal)

        does_service_exist = service_response.does_service_exist

        gprofiler_utils.tokens_queue.put((token_id, service_name, service_id))

        profile_file_name = get_profile_file_name(agent_data.start_time, hostname, is_gz=True)
        profile_file_path = client_handler.join_path(client_handler.get_input_dir(), profile_file_name)

        profile_data = profile.encode()
        profile_file_size = len(profile_data)
        compressed_profile = gzip.compress(profile_data)
        compressed_profile_file_size = len(compressed_profile)
        
        try:
            client_handler.write_file(profile_file_path, compressed_profile)
        except Exception as s3_error:
            logger.error(f"Failed to write profile to S3: {s3_error}")
            raise HTTPException(500, {"message": "Failed to store profile data"})

        service_sample_threshold = db_manager.get_service_sample_threshold_by_id(service_id)
        random_value = random.uniform(0.0, 1.0)

        extra_info = {
            "service_id": service_id,
            "file_size": profile_file_size,
            "compressed_size": compressed_profile_file_size,
            "instance_type": metadata.get("instance_type", ""),
            "version": 2,
        }
        # Down sampler for handling situations with income data overload.
        # Task will be sent to indexer only if generated random value (0.0 to 1.0 range)
        # is greater or equal maximal threshold value which is by default 0 (down sampling off).
        # The threshold could be changed in range 0.0 to 1.0 per client/service.
        if random_value >= service_sample_threshold or "test" in service_name:
            sqs = boto3.client("sqs", config=SQS_CONFIG, endpoint_url=config.SQS_ENDPOINT_URL)
            msg: dict[str, Union[str, int]] = {
                "filename": profile_file_name,
                "service": service_name,
                "service_id": service_id,
            }
            try:
                sqs.send_message(QueueUrl=config.SQS_INDEXER_QUEUE_URL, MessageBody=json.dumps(msg))
                logger.info("send task to queue", extra=extra_info)
            except Exception as sqs_error:
                logger.error(f"Failed to send message to SQS: {sqs_error}")
                raise HTTPException(500, {"message": "Failed to process profile upload"})
        else:
            logger.info("drop task due sampling", extra=extra_info)

    except KeyError as key_error:
        # Client error - missing parameter
        raise HTTPException(400, {"message": f"Missing parameter {key_error}"})
    except HTTPException:
        # HTTPException already handled above (with ignored_failure metric)
        # Let FastAPI handle it without sending additional metrics
        raise
    except Exception as e:
        # Server error - counts against SLO
        if os.path.exists(".debug"):
            import sys
            import traceback

            traceback.print_exception(*sys.exc_info())
        raise

    deployments = [e.split(":")[1] for e in tags if e.startswith(K8S_OBJ_KEY)]
    for deployment in deployments:
        db_manager.get_deployment(service_id, deployment)
    if not does_service_exist:
        try:
            client_handler.register_new_service(service_name)
        except Exception as e:
            logger.exception(
                f"An error has occurred while trying to prepare service: {service_name} "
                f"client: {client_handler} " + repr(e)
            )
            # Server error - counts against SLO
            raise HTTPException(400, {"message": "Failed to register the new service"})
    
    # Success - profile uploaded and processed successfully
    return ProfileResponse(message="ok", gpid=int(gpid))
