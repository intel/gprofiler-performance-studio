#!/bin/sh

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

# Rebuilds the precomputed workload_status Layer 2 (tab counts + coarse-scope
# summaries) and atomically swaps it in. cron invokes this once per minute (~60s
# cadence). The procedure self-guards with an advisory lock, so an in-progress
# build is never queued behind -- a concurrent invocation simply skips.

# cron jobs do not inherit the container env; load the DB connection vars the
# container start-up persisted (see periodic_tasks/Dockerfile).
if [ -f /tmp/cron.env ]; then
    while IFS='=' read -r _k _v; do
        case "$_k" in
            PGHOST|PGPORT|PGUSER|PGPASSWORD|PGDATABASE) export "$_k=$_v" ;;
        esac
    done < /tmp/cron.env
fi

echo "workload snapshot refresh started ($(date -u +%FT%TZ))"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
    -c "CALL refresh_workload_snapshot()"
