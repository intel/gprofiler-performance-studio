--
-- Copyright (C) 2025 Intel Corporation
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
-- ROLLBACK MIGRATION: Remove Dynamic Profiling Feature
-- ============================================================
-- This rollback script removes the dynamic profiling feature
-- and restores the database to its pre-migration state.
--
-- WARNING: This will permanently delete all dynamic profiling data!
--
-- Usage:
--   psql -U performance_studio -d performance_studio -f add_dynamic_profiling.down.sql
--
-- To restore the feature:
--   psql -U performance_studio -d performance_studio -f add_dynamic_profiling.up.sql
-- ============================================================

BEGIN;

-- ============================================================
-- STEP 1: Backup Warning
-- ============================================================

DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'ROLLBACK: Removing Dynamic Profiling Feature';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'This will permanently delete:';
    RAISE NOTICE '  - All profiling requests';
    RAISE NOTICE '  - All profiling commands';
    RAISE NOTICE '  - All profiling executions';
    RAISE NOTICE '  - All host heartbeat data';
    RAISE NOTICE '';
    RAISE NOTICE 'Ensure you have a backup if you need this data!';
    RAISE NOTICE '========================================';
END $$;


-- ============================================================
-- STEP 2: Drop Indexes
-- ============================================================
-- Drop indexes first for cleaner table drops

-- ProfilingExecutions indexes
DROP INDEX IF EXISTS idx_profilingexecutions_status;
DROP INDEX IF EXISTS idx_profilingexecutions_profiling_request_id;
DROP INDEX IF EXISTS idx_profilingexecutions_hostname;
DROP INDEX IF EXISTS idx_profilingexecutions_command_id;

-- ProfilingCommands indexes
DROP INDEX IF EXISTS idx_profilingcommands_hostname_service;
DROP INDEX IF EXISTS idx_profilingcommands_status;
DROP INDEX IF EXISTS idx_profilingcommands_service_name;
DROP INDEX IF EXISTS idx_profilingcommands_hostname;
DROP INDEX IF EXISTS idx_profilingcommands_command_id;

-- ProfilingRequests indexes
DROP INDEX IF EXISTS idx_profilingrequests_created_at;
DROP INDEX IF EXISTS idx_profilingrequests_request_type;
DROP INDEX IF EXISTS idx_profilingrequests_status;
DROP INDEX IF EXISTS idx_profilingrequests_service_name;
DROP INDEX IF EXISTS idx_profilingrequests_request_id;

-- HostHeartbeats indexes
DROP INDEX IF EXISTS idx_hostheartbeats_heartbeat_timestamp;
DROP INDEX IF EXISTS idx_hostheartbeats_status;
DROP INDEX IF EXISTS idx_hostheartbeats_service_name;
DROP INDEX IF EXISTS idx_hostheartbeats_hostname;


-- ============================================================
-- STEP 3: Drop Tables (in correct order for foreign keys)
-- ============================================================

-- Drop ProfilingExecutions first (has FK to ProfilingRequests)
DROP TABLE IF EXISTS ProfilingExecutions CASCADE;

-- Drop ProfilingCommands (no dependencies)
DROP TABLE IF EXISTS ProfilingCommands CASCADE;

-- Drop ProfilingRequests (has FK to Services, referenced by ProfilingExecutions)
DROP TABLE IF EXISTS ProfilingRequests CASCADE;

-- Drop HostHeartbeats (no dependencies)
DROP TABLE IF EXISTS HostHeartbeats CASCADE;


-- ============================================================
-- STEP 4: Drop ENUM Types
-- ============================================================
-- Drop types after tables that use them

DROP TYPE IF EXISTS HostStatus CASCADE;
DROP TYPE IF EXISTS CommandStatus CASCADE;
DROP TYPE IF EXISTS ProfilingRequestStatus CASCADE;
DROP TYPE IF EXISTS ProfilingMode CASCADE;


-- ============================================================
-- STEP 5: Verify Rollback Success
-- ============================================================

DO $$
DECLARE
    remaining_tables integer;
    remaining_types integer;
BEGIN
    -- Count remaining tables
    SELECT COUNT(*) INTO remaining_tables
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name IN ('hostheartbeats', 'profilingrequests', 'profilingcommands', 'profilingexecutions');
    
    -- Count remaining types
    SELECT COUNT(*) INTO remaining_types
    FROM pg_type
    WHERE typname IN ('profilingmode', 'profilingrequeststatus', 'commandstatus', 'hoststatus');
    
    IF remaining_tables > 0 THEN
        RAISE WARNING 'Some tables still exist: %', remaining_tables;
    END IF;
    
    IF remaining_types > 0 THEN
        RAISE WARNING 'Some types still exist: %', remaining_types;
    END IF;
    
    IF remaining_tables = 0 AND remaining_types = 0 THEN
        RAISE NOTICE '========================================';
        RAISE NOTICE 'Rollback completed successfully!';
        RAISE NOTICE '========================================';
        RAISE NOTICE 'Removed:';
        RAISE NOTICE '  - 4 tables (HostHeartbeats, ProfilingRequests, ProfilingCommands, ProfilingExecutions)';
        RAISE NOTICE '  - 4 ENUM types (ProfilingMode, ProfilingRequestStatus, CommandStatus, HostStatus)';
        RAISE NOTICE '  - 14 indexes';
        RAISE NOTICE '';
        RAISE NOTICE 'Database restored to pre-dynamic-profiling state.';
        RAISE NOTICE '========================================';
    ELSE
        RAISE EXCEPTION 'Rollback incomplete: % tables, % types remain', remaining_tables, remaining_types;
    END IF;
END $$;

COMMIT;

-- ============================================================
-- Rollback Complete
-- ============================================================
-- The dynamic profiling feature has been successfully removed.
-- All related tables, types, and indexes have been dropped.
-- ============================================================

