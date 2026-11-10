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
-- MIGRATION: Create flamedb.metrics_ext (cluster mode)
-- ============================================================
-- Adds a table for additional per-host metrics, such as pressure
-- stall information (PSI). It stores one row per metric per profile
-- and keeps data for 90 days.
--
-- Creates flamedb.metrics_ext_local (ReplicatedMergeTree) on every
-- shard and replica, and flamedb.metrics_ext (Distributed, sharded by
-- ServiceId) in front of it, the same layout as flamedb.metrics.
--
-- Until this is applied, the indexer keeps working but drops the
-- additional metrics. Profiles and CPU/memory metrics are not affected.
--
-- Single-node: use add_metrics_ext.up.sql instead.
--
-- Safe to run more than once.
--
-- Usage (from the repository root), against any one node; the
-- ON CLUSTER statements run on all shards and replicas:
--   clickhouse client -u <user> --password <password> --multiquery \
--     < src/gprofiler_indexer/sql/migrations/add_metrics_ext_cluster.up.sql
--
-- Rollback:
--   same command with add_metrics_ext_cluster.down.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS flamedb.metrics_ext_local ON CLUSTER '{cluster}'
(
    Timestamp    DateTime CODEC (DoubleDelta),
    ServiceId    UInt32,
    InstanceType LowCardinality(String),
    HostName     LowCardinality(String),
    HostNameHash UInt32 MATERIALIZED xxHash32(HostName),
    Name         LowCardinality(String),
    Value        Float32
    ) engine = ReplicatedMergeTree('/clickhouse/{installation}/{cluster}/tables/{shard}/{database}/{table}',
                                   '{replica}') PARTITION BY toYYYYMMDD(Timestamp)
    ORDER BY (ServiceId, Name, HostNameHash, Timestamp);

CREATE TABLE IF NOT EXISTS
    flamedb.metrics_ext
    ON CLUSTER '{cluster}' AS
    flamedb.metrics_ext_local
    ENGINE = Distributed('{cluster}', flamedb, metrics_ext_local, ServiceId);

ALTER TABLE flamedb.metrics_ext_local ON CLUSTER '{cluster}'
MODIFY TTL Timestamp + INTERVAL 90 DAY;

-- Verify (on the node you're connected to): metrics_ext_local should
-- contain "TTL Timestamp + toIntervalDay(90)", and metrics_ext should
-- show Distributed(..., metrics_ext_local, ServiceId). The ON CLUSTER
-- output above lists the status of each host.
SELECT name, engine_full FROM system.tables
WHERE database = 'flamedb' AND name IN ('metrics_ext', 'metrics_ext_local');
