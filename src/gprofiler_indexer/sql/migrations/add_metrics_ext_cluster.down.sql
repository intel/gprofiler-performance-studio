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
-- ROLLBACK MIGRATION: Drop flamedb.metrics_ext (cluster mode)
-- ============================================================
-- WARNING: this deletes all stored additional metrics (such as PSI)
-- on every shard and replica. The indexer keeps working without the
-- table, but drops new additional metrics until the table is
-- re-created.
--
-- Drops the Distributed table first, then the local tables. SYNC
-- makes each drop finish right away and removes the replica's Keeper
-- path, so add_metrics_ext_cluster.up.sql can be re-applied
-- immediately afterward.
--
-- Safe to run more than once.
--
-- Usage (from the repository root), against any one node; the
-- ON CLUSTER statements run on all shards and replicas:
--   clickhouse client -u <user> --password <password> --multiquery \
--     < src/gprofiler_indexer/sql/migrations/add_metrics_ext_cluster.down.sql
--
-- Re-apply:
--   same command with add_metrics_ext_cluster.up.sql (the deleted data
--   is not restored)
-- ============================================================

DROP TABLE IF EXISTS flamedb.metrics_ext ON CLUSTER '{cluster}' SYNC;

DROP TABLE IF EXISTS flamedb.metrics_ext_local ON CLUSTER '{cluster}' SYNC;
