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

CONFIG_PROFILES_ROOTDIR = os.getenv("CONFIG_PROFILES_ROOTDIR", "/data/profiles")
TEMP_DIR = os.getenv("TEMP_FILES_DIR", "/data/temp")
FLAMEGRAPH_PATH = os.getenv("FLAMEGRAPH_PATH", "./FlameGraph")

GPROFILER_API_KEY = "GPROFILER-API-KEY"
GPROFILER_SERVICE_NAME = "GPROFILER-SERVICE-NAME"

APP_LOG_FILE_PATH = os.getenv("APP_LOG_FILE_PATH", "backend-logs/log.log")
APP_LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "DEBUG")

SQS_INDEXER_QUEUE_URL = os.getenv("SQS_INDEXER_QUEUE_URL", "")
# boto3 uses as a default sqs url https://queue.amazonaws.com/
# it's a legacy url and doesn't work with private interface for example, this parameter can control the exact url
SQS_ENDPOINT_URL = os.getenv("SQS_ENDPOINT_URL", None)
QUERY_API_BASE_URL = os.getenv("QUERY_API_BASE_URL")

AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
STACKS_COUNT_DEFAULT = int(os.getenv("STACKS_COUNT_DEFAULT", 10000))

REST_VERIFY_TLS = os.getenv("REST_VERIFY_TLS", "TRUE").upper() not in ["FALSE", "0"]
REST_CERTIFICATE_PATH = os.getenv("REST_CERTIFICATE_PATH", REST_VERIFY_TLS)
REST_USERNAME = os.getenv("REST_USERNAME", "")
REST_PASSWORD = os.getenv("REST_PASSWORD", "")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

# Default Slack channels - can be overridden via SLACK_CHANNELS environment variable
# Format: comma-separated list of channel names (e.g., "#general,#alerts,#notifications")
DEFAULT_SLACK_CHANNELS = ["#gprofiler-notifications"]
SLACK_CHANNELS = os.getenv("SLACK_CHANNELS", ",".join(DEFAULT_SLACK_CHANNELS)).split(",")

# Metrics Publisher Configuration
# Enable/disable metrics publishing to metrics agent (similar to gprofiler agent metrics)
# Metrics agent handles batching/queuing on its end, so we send synchronously
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").lower() in ["true", "1", "yes"]
METRICS_AGENT_URL = os.getenv("METRICS_AGENT_URL", "tcp://localhost:18126")
METRICS_SERVICE_NAME = os.getenv("METRICS_SERVICE_NAME", "gprofiler-webapp")
METRICS_SLI_UUID = os.getenv("METRICS_SLI_UUID", None)

BACKEND_ROOT = os.path.dirname(os.path.realpath(__file__))
