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

import os

REDIRECT_DOMAIN = os.getenv("REDIRECT_DOMAIN")


AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")
SESSION_POOL_TIMEOUT = int(os.getenv("SESSION_POOL_TIMEOUT", "600"))

PG_DB_NAME = os.getenv("GPROFILER_POSTGRES_DB_NAME", "mydb")
PG_HOST = os.getenv("GPROFILER_POSTGRES_HOST", "localhost")
PG_USER = os.getenv("GPROFILER_POSTGRES_USERNAME")
PG_PORT = os.getenv("GPROFILER_POSTGRES_PORT", 5432)
PG_PASSWORD = os.getenv("GPROFILER_POSTGRES_PASSWORD")
POSTGRES_CONN_PER_THREAD = os.getenv("GPROFILER_POSTGRES_CONN_PER_THREAD", "FALSE").upper() == "TRUE"
PG_CONNECT_TIMEOUT = int(os.getenv("GPROFILER_POSTGRES_CONNECT_TIMEOUT", 3))

INSTANCE_RUNS_LRU_CACHE_LIMIT = os.getenv("INSTANCE_RUNS_LRU_CACHE_LIMIT", 1000)
PROFILER_PROCESSES_LRU_CACHE_LIMIT = os.getenv("PROFILER_PROCESSES_LRU_CACHE_LIMIT", 1000)


BUCKET_NAME = os.getenv("BUCKET_NAME", "gprofiler")
BASE_DIRECTORY = "products"
# Optional: Custom S3 endpoint for local testing (e.g., LocalStack) or S3-compatible services
# In production, leave unset to use default AWS S3 endpoints
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
