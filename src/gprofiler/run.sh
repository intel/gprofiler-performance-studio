#!/usr/bin/env bash

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

set -ueo pipefail

CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LISTEN_PORT="${NGINX_PORT:-80}"

if [[ "${GUNICORN_PROCESS_COUNT:-}" == "" ]]; then
    GUNICORN_PROCESS_COUNT=$(nproc)
    echo GUNICORN_PROCESS_COUNT not specified. Using "${GUNICORN_PROCESS_COUNT}"
fi
if [[ "${GUNICORN_DD_STATSD_HOST:-}" == "" ]]; then
   GUNICORN_DD_STATSD_HOST="localhost:8125"
   echo GUNICORN_DD_STATSD_HOST not specified. Using "${GUNICORN_DD_STATSD_HOST}"
fi
if [[ "${GUNICORN_MAX_REQUESTS:-}" == "" ]]; then
   GUNICORN_MAX_REQUESTS=10000
   echo GUNICORN_MAX_REQUESTS not specified. Using "${GUNICORN_MAX_REQUESTS}"
fi
if [[ "${GUNICORN_LOG_LEVEL:-}" == "" ]]; then
    GUNICORN_LOG_LEVEL="warning"
   echo GUNICORN_LOG_LEVEL not specified. Using "${GUNICORN_LOG_LEVEL}"
fi
gunicorn_pid_file=/var/run/gunicorn.pid

gunicorn_cmd_line=" --workers=${GUNICORN_PROCESS_COUNT} \
               --bind=unix:/tmp/mysite.sock \
               --worker-class=uvicorn.workers.UvicornWorker \
               --statsd-host=${GUNICORN_DD_STATSD_HOST} \
               --name=gprofiler_gunicorn \
               --max-requests=${GUNICORN_MAX_REQUESTS} \
               --max-requests-jitter=1000 \
               --timeout=300 \
               --preload \
               --forwarded-allow-ips='*' \
               --log-level=${GUNICORN_LOG_LEVEL} \
               --pid=${gunicorn_pid_file}"

function clean_up {
    kill "${GUNICORN_PID}"
    kill "${NGINX_PID}"
    exit
}
trap clean_up SIGHUP SIGINT SIGTERM
rm -f ${gunicorn_pid_file}

cd ${CURRENT_DIR} && gunicorn backend.main:app ${gunicorn_cmd_line} &
GUNICORN_PID=$!

sed -i -E "s/listen [0-9]+/listen ${LISTEN_PORT}/" /etc/nginx/nginx.conf
nginx -g "daemon off;" &
NGINX_PID=$!

wait ${GUNICORN_PID} ${NGINX_PID}
