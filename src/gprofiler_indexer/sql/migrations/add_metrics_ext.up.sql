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
-- MIGRATION: Create flamedb.metrics_ext (single-node)
-- ============================================================
-- Adds a table for additional per-host metrics, such as pressure
-- stall information (PSI). It stores one row per metric per profile
-- and keeps data for 90 days.
--
-- Until this is applied, the indexer keeps working but drops the
-- additional metrics. Profiles and CPU/memory metrics are not affected.
--
-- Cluster mode: use add_metrics_ext_cluster.up.sql instead.
--
-- Safe to run more than once.
--
-- Usage (from the deploy/ directory):
--   docker exec -i gprofiler-ps-clickhouse bash -c \
--     'clickhouse-client -u "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" -mn' \
--     < ../src/gprofiler_indexer/sql/migrations/add_metrics_ext.up.sql
--
-- Rollback:
--   same command with add_metrics_ext.down.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS flamedb.metrics_ext
(
    Timestamp    DateTime('UTC') CODEC (DoubleDelta),
    ServiceId    UInt32,
    InstanceType LowCardinality(String),
    HostName     LowCardinality(String),
    HostNameHash UInt32 MATERIALIZED xxHash32(HostName),
    Name         LowCardinality(String),
    Value        Float32
) engine = MergeTree() PARTITION BY toYYYYMMDD(Timestamp)
      ORDER BY (ServiceId, Name, HostNameHash, Timestamp);

ALTER TABLE flamedb.metrics_ext
    MODIFY TTL "Timestamp" + INTERVAL 90 DAY;

-- Verify: the output should contain "TTL Timestamp + toIntervalDay(90)"
SELECT engine_full FROM system.tables
WHERE database = 'flamedb' AND name = 'metrics_ext';
