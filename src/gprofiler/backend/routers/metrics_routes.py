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

import json
import math
import uuid
from datetime import datetime, timedelta
from logging import getLogger
from typing import List, Optional

from backend.models.filters_models import FilterTypes
from backend.models.flamegraph_models import FGParamsBaseModel
from backend.models.metrics_models import (
    CommandCompletionRequest,
    CpuMetric,
    CpuTrend,
    HeartbeatRequest,
    HeartbeatResponse,
    HTMLMetadata,
    InstanceTypeCount,
    MetricGraph,
    MetricNodesAndCores,
    MetricNodesCoresSummary,
    MetricSummary,
    ProfilingHostStatus,
    ProfilingHostStatusRequest,
    ProfilingRequest,
    ProfilingResponse,
    SampleCount,
)
from backend.utils.filters_utils import get_rql_first_eq_key, get_rql_only_for_one_key
from backend.utils.notifications import SlackNotifier
from backend.utils.request_utils import flamegraph_base_request_params, get_metrics_response, get_query_response
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from gprofiler_dev import S3ProfileDal
from gprofiler_dev.postgres.db_manager import DBManager

logger = getLogger(__name__)
router = APIRouter()


def get_time_interval_value(start_time: datetime, end_time: datetime, interval: str) -> str:
    if interval in [
        "15 seconds",
        "30 seconds",
        "1 minutes",
        "5 minutes",
        "15 minutes",
        "1 hours",
        "2 hours",
        "6 hours",
        "24 hours",
    ]:
        return interval
    diff = end_time - start_time
    value = diff.total_seconds()
    if value <= 60 * 30:  # half an hour
        return "15 seconds"
    if value <= 60 * 60:  # hour
        return "30 seconds"
    if value <= 60 * 60 * 24:  # day
        return "15 minutes"
    if value <= 60 * 60 * 24 * 7:  # week
        return "2 hours"
    if value <= 60 * 60 * 24 * 14:  # 2 weeks
        return "6 hours"
    return "24 hours"


def profiling_host_status_params(
    service_name: Optional[List[str]] = Query(None, description="Filter by service name(s)"),
    exact_match: bool = Query(False, description="Use exact match for service name (default: false for partial matching)"),
    hostname: Optional[List[str]] = Query(None, description="Filter by hostname(s)"),
    ip_address: Optional[List[str]] = Query(None, description="Filter by IP address(es)"),
    profiling_status: Optional[List[str]] = Query(None, description="Filter by profiling status(es) (e.g., pending, completed, stopped)"),
    command_type: Optional[List[str]] = Query(None, description="Filter by command type(s) (e.g., start, stop)"),
    pids: Optional[List[int]] = Query(None, description="Filter by PIDs"),
) -> ProfilingHostStatusRequest:
    return ProfilingHostStatusRequest(
        service_name=service_name,
        exact_match=exact_match,
        hostname=hostname,
        ip_address=ip_address,
        profiling_status=profiling_status,
        command_type=command_type,
        pids=pids,
    )


@router.get("/instance_type_count", response_model=List[InstanceTypeCount])
def get_instance_type_count(fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params)):
    response = get_query_response(fg_params, lookup_for="instance_type_count")
    res = []
    for row in response:
        res.append(
            {
                "instance_count": row.get("instance_count", 0),
                "instance_type": row.get("instance_type", "").split("/")[-1],
            }
        )
    return res


@router.get("/samples", response_model=List[SampleCount])
def get_flamegraph_samples_count(
    requested_interval: Optional[str] = "",
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    return get_query_response(fg_params, lookup_for="samples", interval=requested_interval)


@router.get(
    "/graph", response_model=List[MetricGraph], responses={204: {"description": "Good request, just has no data"}}
)
def get_flamegraph_metrics_graph(
    requested_interval: Optional[str] = "",
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)
    if deployment_name:
        return Response(status_code=204)
    fg_params.filter = get_rql_only_for_one_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
    return get_metrics_response(fg_params, lookup_for="graph", interval=requested_interval)


@router.get(
    "/function_cpu",
    response_model=List[CpuMetric],
    responses={204: {"description": "Good request, just has no data"}},
)
def get_function_cpu_overtime(
    function_name: str = Query(..., alias="functionName"),
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    fg_params.function_name = function_name
    return get_query_response(fg_params, lookup_for="samples_count_by_function")


@router.get(
    "/graph/nodes_and_cores",
    response_model=List[MetricNodesAndCores],
    responses={204: {"description": "Good request, just has no data"}},
)
def get_flamegraph_nodes_cores_graph(
    requested_interval: str = "",
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)
    container_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.CONTAINER_KEY)
    host_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)

    if deployment_name or container_name_value:
        return Response(status_code=204)

    db_manager = DBManager()
    service_id = db_manager.get_service_id_by_name(fg_params.service_name)
    parsed_interval_value = get_time_interval_value(fg_params.start_time, fg_params.end_time, requested_interval)
    return db_manager.get_nodes_and_cores_graph(
        service_id, fg_params.start_time, fg_params.end_time, parsed_interval_value, host_name_value
    )


@router.get(
    "/summary",
    response_model=MetricSummary,
    response_model_exclude_none=True,
    responses={204: {"description": "Good request, just has no data"}},
)
def get_metrics_summary(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)

    if not deployment_name:  # hostname before deployment or no filters at all
        fg_params.filter = get_rql_only_for_one_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
        return get_metrics_response(fg_params, lookup_for="summary")

    return Response(status_code=204)


@router.get(
    "/nodes_cores/summary",
    response_model=MetricNodesCoresSummary,
    response_model_exclude_none=True,
    responses={204: {"description": "Good request, just has no data"}},
)
def get_nodes_and_cores_metrics_summary(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
    ignore_zeros: bool = Query(False, alias="ignoreZeros"),
):
    db_manager = DBManager()
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)
    if not deployment_name:  # hostname before deployment or no filters at all

        service_id = db_manager.get_service_id_by_name(fg_params.service_name)
        host_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
        res = db_manager.get_nodes_cores_summary(
            service_id, fg_params.start_time, fg_params.end_time, ignore_zeros=ignore_zeros, hostname=host_name_value
        )
        if res["avg_cores"] is None and res["avg_nodes"] is None:
            return Response(status_code=204)
        return res

    return Response(status_code=204)


@router.get("/cpu_trend", response_model=CpuTrend)
def calculate_trend_in_cpu(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    diff_in_days: int = (fg_params.end_time - fg_params.start_time).days
    diff_in_hours: float = (fg_params.end_time - fg_params.start_time).seconds / 3600
    diff_in_weeks = timedelta(weeks=1)

    # if the time range is longer then onw week we would like to increase the delta in x +1 weeks from the current range
    if diff_in_days >= 7:
        weeks = math.ceil(diff_in_days / 7)
        # If it is exactly X weeks diff, verify that it is exactly X weeks diff without hours, otherwise add 1 week
        if diff_in_days % 7 == 0 and diff_in_hours > 0:
            weeks += 1
        diff_in_weeks = timedelta(weeks=weeks)
    compared_start_date = fg_params.start_time - diff_in_weeks
    compared_end_date = fg_params.end_time - diff_in_weeks

    response = get_metrics_response(
        fg_params,
        lookup_for="cpu_trend",
        compared_start_datetime=compared_start_date.strftime("%Y-%m-%dT%H:%M:%S"),
        compared_end_datetime=compared_end_date.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    return response


@router.get("/html_metadata", response_model=HTMLMetadata)
def get_html_metadata(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    host_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
    if not host_name_value:
        raise HTTPException(400, detail="Must filter by hostname to get the html metadata")
    s3_path = get_metrics_response(fg_params, lookup_for="lasthtml")
    if not s3_path:
        raise HTTPException(404, detail="The html metadata path not found in CH")
    s3_dal = S3ProfileDal(logger)
    try:
        html_content = s3_dal.get_object(s3_path, is_gzip=True)
    except ClientError:
        raise HTTPException(status_code=404, detail="The html metadata file not found in S3")
    return HTMLMetadata(content=html_content)


@router.post("/profile_request", response_model=ProfilingResponse)
def create_profiling_request(profiling_request: ProfilingRequest) -> ProfilingResponse:
    """
    Create a new profiling request with the specified parameters.

    This endpoint accepts profiling arguments in JSON format and handles both
    start and stop profiling commands. Each request generates a unique command_id
    that agents use for idempotency - agents will only execute commands with
    new command IDs they haven't seen before.

    START commands:
    - Create new profiling sessions with specified parameters
    - Merge multiple requests for the same host into single commands

    STOP commands:
    - Process-level stop: Remove specific PIDs from existing commands
      - If only one PID remains, convert to host-level stop
      - If multiple PIDs remain, update command with remaining PIDs
    - Host-level stop: Stop entire profiling session for the host
    """
    try:
        # Log the profiling request
        logger.info(
            f"Received {profiling_request.request_type} profiling request for service: {profiling_request.service_name}",
            extra={
                "request_type": profiling_request.request_type,
                "service_name": profiling_request.service_name,
                "continuous": profiling_request.continuous,
                "duration": profiling_request.duration,
                "frequency": profiling_request.frequency,
                "mode": profiling_request.profiling_mode,
                "target_hosts": profiling_request.target_hosts,
                "stop_level": profiling_request.stop_level,
            },
        )

        db_manager = DBManager()
        request_id = str(uuid.uuid4())
        command_ids = []  # Track all command IDs created

        try:
            # Convert target_hosts to legacy format for database compatibility
            target_hostnames = list(profiling_request.target_hosts.keys()) if profiling_request.target_hosts else None
            host_pid_mapping = (
                {hostname: pids for hostname, pids in profiling_request.target_hosts.items() if pids}
                if profiling_request.target_hosts
                else None
            )

            # Save the profiling request to database using enhanced method
            success = db_manager.save_profiling_request(
                request_id=request_id,
                request_type=profiling_request.request_type,
                service_name=profiling_request.service_name,
                continuous=profiling_request.continuous,
                duration=profiling_request.duration,
                frequency=profiling_request.frequency,
                profiling_mode=profiling_request.profiling_mode,
                target_hostnames=target_hostnames,
                pids=None,  # Deprecated field, always None
                host_pid_mapping=host_pid_mapping,
                additional_args=profiling_request.additional_args,
            )

            if not success:
                raise Exception("Failed to save profiling request to database")

            # Handle start vs stop commands differently
            if profiling_request.request_type == "start":
                # Create profiling commands for target hosts
                target_hosts = []

                # Determine target hosts from target_hosts mapping
                if profiling_request.target_hosts:
                    target_hosts = list(profiling_request.target_hosts.keys())

                if target_hosts:
                    # Create commands for specific hosts
                    for hostname in target_hosts:
                        command_id = str(uuid.uuid4())
                        command_ids.append(command_id)
                        db_manager.create_or_update_profiling_command(
                            command_id=command_id,
                            hostname=hostname,
                            service_name=profiling_request.service_name,
                            command_type="start",
                            new_request_id=request_id,
                        )
                else:
                    # If no specific hostnames, create command for all hosts of this service
                    command_id = str(uuid.uuid4())
                    command_ids.append(command_id)
                    db_manager.create_or_update_profiling_command(
                        command_id=command_id,
                        hostname=None,  # Will be handled for all hosts of the service
                        service_name=profiling_request.service_name,
                        command_type="start",
                        new_request_id=request_id,
                    )

            elif profiling_request.request_type == "stop":
                # Handle stop commands with host-to-PID associations
                target_hosts = []

                # Determine target hosts for stop commands
                if profiling_request.target_hosts:
                    target_hosts = list(profiling_request.target_hosts.keys())

                if target_hosts:
                    for hostname in target_hosts:
                        command_id = str(uuid.uuid4())
                        command_ids.append(command_id)

                        if profiling_request.stop_level == "host":
                            # Stop entire host
                            db_manager.create_stop_command_for_host(
                                command_id=command_id,
                                hostname=hostname,
                                service_name=profiling_request.service_name,
                                request_id=request_id,
                            )
                        else:  # process level stop
                            # Get PIDs for this specific host from target_hosts mapping
                            host_pids = None
                            if profiling_request.target_hosts and hostname in profiling_request.target_hosts:
                                host_pids = profiling_request.target_hosts[hostname]

                            # Stop specific processes for this host
                            db_manager.handle_process_level_stop(
                                command_id=command_id,
                                hostname=hostname,
                                service_name=profiling_request.service_name,
                                pids_to_stop=host_pids,
                                request_id=request_id,
                            )
                else:
                    # No specific hosts provided - this should be rare for stop commands
                    logger.warning(f"Stop request {request_id} has no target hosts specified")
                    raise HTTPException(status_code=400, detail="Stop commands require specific target hosts")

            logger.info(
                f"Profiling request {request_id} ({profiling_request.request_type}) saved and commands processed. Command IDs: {command_ids}"
            )

        except Exception as e:
            logger.error(f"Failed to save profiling request: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to save profiling request to database")

        # Calculate estimated completion time (only for start commands)
        completion_time = None
        if profiling_request.request_type == "start":
            completion_time = datetime.now() + timedelta(seconds=profiling_request.duration or 60)

        # Create appropriate message based on number of commands
        if len(command_ids) == 1:
            message = f"{profiling_request.request_type.capitalize()} profiling request submitted successfully for service '{profiling_request.service_name}'"
        else:
            message = f"{profiling_request.request_type.capitalize()} profiling request submitted successfully for service '{profiling_request.service_name}' across {len(command_ids)} hosts"

        # Send Slack notification for profiling request creation
        try:
            slack_notifier = SlackNotifier()

            # Create rich message blocks
            blocks = _create_slack_blocks(profiling_request, request_id)

            slack_notifier.send_rich_message_to_all_channels(blocks=blocks, text=message)
        except Exception as e:
            logger.warning(f"Failed to send Slack notification for profiling request {request_id}: {e}")

        return ProfilingResponse(
            success=True,
            message=message,
            request_id=request_id,
            command_ids=command_ids,
            estimated_completion_time=completion_time,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to create profiling request: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while processing profiling request")


def _create_slack_blocks(profiling_request: ProfilingRequest, request_id: str) -> list:
    """
    Create Slack message blocks for profiling request notifications.

    Args:
        profiling_request: The profiling request object
        request_id: The unique request identifier

    Returns:
        List of Slack message blocks
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔥 Profiling Request for service {profiling_request.service_name}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"A new request was made to {profiling_request.request_type} a profile and the details are shown below:"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service Name:*\n{profiling_request.service_name}"},
                {"type": "mrkdwn", "text": f"*Request ID:*\n{request_id}"},
            ],
        },
    ]

    # Add hosts and PIDs information in a single block
    if profiling_request.target_hosts:
        hosts_info = []
        for host, pids in profiling_request.target_hosts.items():
            if pids:
                pids_str = ", ".join(map(str, pids))
                hosts_info.append(f"• {host} - PIDs: {pids_str}")
            else:
                hosts_info.append(f"• {host} - Host level profiling")

        if hosts_info:
            hosts_text = "\n".join(hosts_info)
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Target Hosts:*\n{hosts_text}"}})

    return blocks


@router.post("/heartbeat", response_model=HeartbeatResponse)
def receive_heartbeat(heartbeat: HeartbeatRequest):
    """
    Receive heartbeat from host and check for current profiling requests.

    This endpoint:
    1. Receives heartbeat information from hosts (IP, hostname, service, last command)
    2. Updates host status in PostgreSQL DB
    3. Checks for current profiling requests for this host/service
    4. Returns new profiling request if available
    """
    try:
        # Set timestamp if not provided
        if heartbeat.timestamp is None:
            heartbeat.timestamp = datetime.now()

        # Log the heartbeat
        logger.info(
            f"Received heartbeat from host: {heartbeat.hostname} ({heartbeat.ip_address})",
            extra={
                "hostname": heartbeat.hostname,
                "ip_address": heartbeat.ip_address,
                "service_name": heartbeat.service_name,
                "last_command_id": heartbeat.last_command_id,
                "status": heartbeat.status,
                "timestamp": heartbeat.timestamp,
            },
        )

        db_manager = DBManager()

        try:
            # 1. Update host heartbeat information in PostgreSQL DB
            db_manager.upsert_host_heartbeat(
                hostname=heartbeat.hostname,
                ip_address=heartbeat.ip_address,
                service_name=heartbeat.service_name,
                last_command_id=heartbeat.last_command_id,
                status=heartbeat.status,
                heartbeat_timestamp=heartbeat.timestamp,
            )

            # 2. Check for current profiling command for this host/service
            current_command = db_manager.get_current_profiling_command(
                hostname=heartbeat.hostname,
                service_name=heartbeat.service_name,
            )

            if current_command:
                success = True
                if current_command["status"] == "pending":
                    # 3. Mark command as sent and update related request statuses
                    success = db_manager.mark_profiling_command_sent(
                        command_id=current_command["command_id"], hostname=heartbeat.hostname
                    )

                    # 4. Mark related profiling requests as assigned
                    if success and current_command.get("request_ids"):
                        request_ids = current_command["request_ids"]
                        # Parse the request_ids array if it exists
                        if request_ids:
                            try:
                                if isinstance(request_ids, str):
                                    # PostgreSQL array format: {uuid1,uuid2,uuid3}
                                    # Remove braces and split by comma
                                    request_ids_str = request_ids.strip("{}")
                                    if request_ids_str:
                                        request_ids = [uuid.strip() for uuid in request_ids_str.split(",")]
                                    else:
                                        request_ids = []
                            except Exception:
                                logger.warning(
                                    f"Failed to parse request_ids for command {current_command['command_id']}"
                                )
                                request_ids = []

                        for request_id in request_ids:
                            try:
                                db_manager.mark_profiling_request_assigned(
                                    request_id=request_id,
                                    command_id=current_command["command_id"],
                                    hostname=heartbeat.hostname,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to mark request {request_id} as assigned: {e}")

                if success:
                    logger.info(
                        f"Sending profiling command {current_command['command_id']} to host {heartbeat.hostname}"
                    )

                    # Extract combined_config and ensure it's properly formatted
                    combined_config = current_command.get("combined_config", {})

                    # If combined_config is a string (from DB), parse it
                    if isinstance(combined_config, str):
                        try:
                            combined_config = json.loads(combined_config)
                        except json.JSONDecodeError:
                            logger.warning(
                                f"Failed to parse combined_config for command {current_command['command_id']}"
                            )
                            combined_config = {}

                    return HeartbeatResponse(
                        success=True,
                        message="Heartbeat received. New profiling command available.",
                        profiling_command={
                            "command_type": current_command["command_type"],
                            "combined_config": combined_config,
                        },
                        command_id=current_command["command_id"],
                    )
                else:
                    logger.warning(
                        f"Failed to mark command {current_command['command_id']} as sent to host {heartbeat.hostname}"
                    )

            # No commands or marking failed
            return HeartbeatResponse(
                success=True,
                message="Heartbeat received. No profiling commands.",
                profiling_command=None,
                command_id=None,
            )

        except Exception as e:
            logger.error(f"Failed to process heartbeat for {heartbeat.hostname}: {e}", exc_info=True)
            # Still return success for heartbeat, but no command
            return HeartbeatResponse(
                success=True,
                message="Heartbeat received, but failed to check for commands.",
                profiling_command=None,
                command_id=None,
            )

    except Exception as e:
        logger.error(f"Failed to process heartbeat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while processing heartbeat")


@router.post("/command_completion")
def report_command_completion(completion: CommandCompletionRequest):
    """
    Report completion of a profiling command from a host.

    This endpoint:
    1. Receives command completion status from hosts
    2. Validates that the command exists for the specific host
    3. Updates command status in PostgreSQL DB
    4. Updates related profiling requests status
    """
    try:
        db_manager = DBManager()

        # Log the completion
        logger.info(
            f"Received command completion from host: {completion.hostname}",
            extra={
                "command_id": completion.command_id,
                "hostname": completion.hostname,
                "status": completion.status,
                "execution_time": completion.execution_time,
                "error_message": completion.error_message,
            },
        )

        # Validate that the command can be completed (exists and is in assigned status)
        is_valid, error_message = db_manager.validate_command_completion_eligibility(
            completion.command_id, completion.hostname
        )
        if not is_valid:
            logger.warning(f"Command completion validation failed: {error_message}")
            return {"success": False, "message": error_message}

        # Update the command status
        # The command_id reported by the CommandCompletionRequest can be outdated
        # Meaning that the current command for the hostname might not be the one reported by the command completion (common at profiling restarts due to new profiling requests)
        # For those cases, this update will not change any row at the commands table
        db_manager.update_profiling_command_status(
            command_id=completion.command_id,
            hostname=completion.hostname,
            status=completion.status,
            execution_time=completion.execution_time,
            error_message=completion.error_message,
            results_path=completion.results_path,
        )

        # Update the specific profiling execution record for the command_id reported by the CommandCompletionRequest
        completed_at = datetime.now() if completion.status in ["completed", "failed"] else None
        db_manager.update_profiling_execution_status(
            command_id=completion.command_id,
            hostname=completion.hostname,
            status=completion.status,
            completed_at=completed_at,
            error_message=completion.error_message,
            execution_time=completion.execution_time,
            results_path=completion.results_path,
        )

        # Get current profiling command to to verify if the command_id corresponds the one reported by the CommandCompletionRequest
        current_command = db_manager.get_profiling_command_by_hostname(completion.hostname)
        outdated_command = current_command is None or (
            current_command and current_command["command_id"] != completion.command_id
        )
        # If the command is outdated, we don't need to update the request status of each request related to the command
        # The request status will be updated when the most recent command_id is completed
        if not outdated_command and current_command is not None:
            # Update related profiling requests status
            db_manager.auto_update_profiling_request_status_by_request_ids(current_command["request_ids"])

        return {"success": True, "message": f"Command completion recorded for {completion.command_id}"}

    except Exception as e:
        logger.error(f"Failed to process command completion: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while processing command completion")


@router.get("/profiling/host_status", response_model=List[ProfilingHostStatus])
def get_profiling_host_status(
    profiling_params: ProfilingHostStatusRequest = Depends(profiling_host_status_params),
):
    """
    Get profiling host status with optional filtering by multiple parameters.
    Uses optimized single-query approach with JOINs instead of N+1 queries.

    Performance improvements:
    - Single database query instead of N+1 (1 query + 1 per host)
    - Database-side filtering for all parameters
    - LEFT JOIN between HostHeartbeats and ProfilingCommands
    - 10-50x faster response time

    Args:
        profiling_params: ProfilingHostStatusRequest object containing all filter parameters

    Returns:
        List of host statuses filtered by the specified criteria
    """
    db_manager = DBManager()

    # Use the optimized method that performs filtering and joining in the database
    hosts = db_manager.get_profiling_host_status_optimized(
        service_names=profiling_params.service_name,
        hostnames=profiling_params.hostname,
        ip_addresses=profiling_params.ip_address,
        profiling_statuses=profiling_params.profiling_status,
        command_types=profiling_params.command_type,
        pids=profiling_params.pids,
        exact_match=profiling_params.exact_match
    )

    # Convert database results to response model
    results = []
    for host in hosts:
        # Extract PIDs from combined_config
        combined_config = host.get("combined_config")
        command_pids = []

        if combined_config:
            if isinstance(combined_config, str):
                try:
                    combined_config = json.loads(combined_config)
                except json.JSONDecodeError:
                    combined_config = {}

            if isinstance(combined_config, dict):
                pids_in_config = combined_config.get("pids", [])
                if isinstance(pids_in_config, list):
                    command_pids = [int(pid) for pid in pids_in_config if str(pid).isdigit()]

        # Handle NULL status (no command) as "stopped"
        profiling_status = host.get("status") or "stopped"
        command_type = host.get("command_type") or "N/A"

        results.append(
            ProfilingHostStatus(
                id=host.get("id", 0),
                service_name=host.get("service_name"),
                hostname=host.get("hostname"),
                ip_address=host.get("ip_address"),
                pids=command_pids,
                command_type=command_type,
                profiling_status=profiling_status,
                heartbeat_timestamp=host.get("heartbeat_timestamp"),
            )
        )

    return results
