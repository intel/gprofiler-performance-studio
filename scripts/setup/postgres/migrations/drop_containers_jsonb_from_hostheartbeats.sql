--
-- Copyright (C) 2023 Intel Corporation
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

-- Drop the transitional HostHeartbeats.containers JSONB snapshot.
--
-- Workload inventory now lives entirely in the normalized HeartbeatContainers /
-- HeartbeatProcesses tables (see add_structured_workload_inventory_tables.sql).
--
-- DEPLOY ORDERING: apply this migration only AFTER the application code that no
-- longer reads or writes the containers column is live. The current heartbeat
-- write path stops populating this column and the read path no longer selects it,
-- so once that build is deployed the column is dead and safe to drop.

ALTER TABLE HostHeartbeats
DROP COLUMN IF EXISTS containers;
