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

ALTER TABLE HostHeartbeats
ADD COLUMN IF NOT EXISTS agent_version text NULL,
ADD COLUMN IF NOT EXISTS run_mode text NULL,
ADD COLUMN IF NOT EXISTS namespace text NULL,
ADD COLUMN IF NOT EXISTS pod_name text NULL,
ADD COLUMN IF NOT EXISTS containers jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_hostheartbeats_namespace ON HostHeartbeats (namespace);
CREATE INDEX IF NOT EXISTS idx_hostheartbeats_pod_name ON HostHeartbeats (pod_name);
