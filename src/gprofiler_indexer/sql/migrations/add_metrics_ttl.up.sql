--
-- Copyright (C) 2026 Intel Corporation
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--    http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--

-- ============================================================
-- MIGRATION: Add a 90-day TTL to flamedb.metrics (single-node)
-- ============================================================
-- Older single-node installs keep flamedb.metrics forever. This adds
-- 90-day retention.
--
-- Cluster mode: clusters created from a schema that includes commit
-- cb85c25 (#92) already have this TTL on flamedb.metrics_local. For
-- older clusters, see deploy/README.md, section 3.
--
-- Safe to run more than once. Applying it removes rows older than
-- 90 days.
--
-- Usage (from the deploy/ directory):
--   docker exec -i gprofiler-ps-clickhouse bash -c \
--     'clickhouse-client -u "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" -mn' \
--     < ../src/gprofiler_indexer/sql/migrations/add_metrics_ttl.up.sql
--
-- Rollback:
--   same command with add_metrics_ttl.down.sql
-- ============================================================

ALTER TABLE flamedb.metrics
    MODIFY TTL "Timestamp" + INTERVAL 90 DAY;

-- Verify: the output should contain "TTL Timestamp + toIntervalDay(90)"
SELECT engine_full FROM system.tables
WHERE database = 'flamedb' AND name = 'metrics';
