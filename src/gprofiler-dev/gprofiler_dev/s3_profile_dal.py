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
from datetime import datetime
from io import BytesIO
from typing import Callable, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dateutil.relativedelta import relativedelta
from gprofiler_dev import config
from gprofiler_dev.boto3_utils import boto3_lock

IsFileRelevantFunction = Callable[[str, relativedelta, Optional[int], datetime], Optional[bool]]
DEFAULT_OUTPUT_FOLDER_NAME = "flames"


class S3ProfileDal:
    def __init__(
        self,
        logger,
        session: boto3.Session = None,
        input_folder_name: str = "stacks",
    ):
        self.logger = logger
        self.bucket_name = config.BUCKET_NAME
        self.base_directory = config.BASE_DIRECTORY
        self.input_folder_name = input_folder_name
        if session is None:
            with boto3_lock:
                session = boto3.Session(
                    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
                    aws_session_token=config.AWS_SESSION_TOKEN,
                )
        # endpoint_url allows connecting to LocalStack or S3-compatible services for testing
        # When None (default), uses standard AWS S3 endpoints
        self._s3_client = session.client("s3", config=Config(max_pool_connections=50), endpoint_url=config.S3_ENDPOINT_URL)
        self._s3_resource = session.resource("s3", endpoint_url=config.S3_ENDPOINT_URL)

    @staticmethod
    def join_path(*parts: str) -> str:
        return "/".join(parts)

    def get_service_dir_path(self, service_name: str, dir_name: str = None):
        service_path = self.join_path(self.base_directory, service_name)
        if dir_name is None:
            return service_path
        return self.join_path(service_path, dir_name)

    def get_input_dir(self, service_name: str) -> str:
        return self.get_service_dir_path(service_name, self.input_folder_name)

    def download_file(self, src_file_path: str, dest_file_path: str) -> None:
        assert src_file_path and dest_file_path, "Invalid file paths given"
        try:
            self._s3_resource.Bucket(self.bucket_name).download_file(src_file_path, dest_file_path)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise FileNotFoundError("Requested file does not exist", src_file_path) from error
            raise

    def get_object(self, s3_path: str, is_gzip=False) -> str:
        s3_response = self._s3_client.get_object(Bucket=self.bucket_name, Key=s3_path)
        response_body = s3_response["Body"].read()
        if is_gzip:
            with gzip.GzipFile(fileobj=BytesIO(response_body)) as gz:
                response_body = gz.read()
        return response_body.decode("utf-8")

    def write_file(self, file_path: str, content: bytes) -> None:
        io_content = BytesIO(content)
        self._s3_client.upload_fileobj(Bucket=self.bucket_name, Fileobj=io_content, Key=file_path)

    def upload_file(self, local_path: str, dest_path: str) -> None:
        self._s3_client.upload_file(local_path, self.bucket_name, dest_path)
