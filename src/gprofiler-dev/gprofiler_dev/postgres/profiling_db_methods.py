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

"""
Database methods for profiling requests and commands management.
These methods should be added to the DBManager class or used as a mixin.
"""

import json
import uuid
from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional

logger = getLogger(__name__)


class ProfilingDBMethods:
    """Mixin class for profiling-related database operations"""

    def get_connection(self):
        """Return a database connection. Override or implement in subclass."""
        raise NotImplementedError("get_connection() must be implemented in the DBManager or subclass.")

    def save_profiling_request(
        self,
        request_id: str,
        service_name: str,
        duration: Optional[int] = None,
        frequency: Optional[int] = None,
        profiling_mode: Optional[str] = None,
        target_hostnames: Optional[List[str]] = None,
        pids: Optional[List[int]] = None,
        additional_args: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save a profiling request to the database"""
        query = """
            INSERT INTO ProfilingRequests (
                request_id, service_name, duration, frequency, profiling_mode,
                target_hostnames, pids, additional_args
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING request_id
        """

        params = (
            request_id,
            service_name,
            duration,
            frequency,
            profiling_mode,
            target_hostnames,
            pids,
            json.dumps(additional_args) if additional_args else None,
        )

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    conn.commit()
                    logger.info(f"Saved profiling request {request_id}")
                    return result[0]
        except Exception as e:
            logger.error(f"Failed to save profiling request {request_id}: {e}")
            raise

    def create_or_update_profiling_command(self, hostname: Optional[str], service_name: str, new_request_id: str):
        """Create or update a profiling command for a host, combining multiple requests"""

        if hostname is None:
            # Get all active hosts for this service
            hosts = self._get_active_hosts_for_service(service_name)
        else:
            hosts = [hostname]

        for host in hosts:
            # Check if there's already a pending command for this host
            existing_command = self._get_pending_command_for_host(host, service_name)

            if existing_command:
                # Update existing command by adding the new request
                self._add_request_to_command(existing_command["command_id"], new_request_id)
            else:
                # Create new command
                self._create_new_profiling_command(host, service_name, [new_request_id])

    def _get_active_hosts_for_service(self, service_name: str) -> List[str]:
        """Get list of active hosts for a service"""
        query = """
            SELECT DISTINCT hostname
            FROM HostHeartbeats
            WHERE service_name = %s
            AND status = 'active'
            AND heartbeat_timestamp > CURRENT_TIMESTAMP - INTERVAL '5 minutes'
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (service_name,))
                    results = cursor.fetchall()
                    return [row[0] for row in results]
        except Exception as e:
            logger.error(f"Failed to get active hosts for service {service_name}: {e}")
            return []

    def _get_pending_command_for_host(self, hostname: str, service_name: str) -> Optional[Dict]:
        """Get pending command for a specific host"""
        query = """
            SELECT command_id, combined_config, request_ids
            FROM ProfilingCommands
            WHERE hostname = %s AND service_name = %s AND status = 'pending'
            ORDER BY created_at DESC
            LIMIT 1
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (hostname, service_name))
                    result = cursor.fetchone()
                    if result:
                        return {"command_id": result[0], "combined_config": result[1], "request_ids": result[2]}
                    return None
        except Exception as e:
            logger.error(f"Failed to get pending command for host {hostname}: {e}")
            return None

    def _add_request_to_command(self, command_id: str, new_request_id: str):
        """Add a new request to an existing command"""
        # First, get the current request details
        request_query = """
            SELECT duration, frequency, profiling_mode, pids, additional_args
            FROM ProfilingRequests
            WHERE request_id = %s
        """

        # Update command with new request
        update_query = """
            UPDATE ProfilingCommands
            SET request_ids = array_append(request_ids, %s),
                combined_config = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE command_id = %s
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get new request details
                    cursor.execute(request_query, (new_request_id,))
                    request_data = cursor.fetchone()

                    if request_data:
                        # Get current command config
                        cursor.execute(
                            "SELECT combined_config FROM ProfilingCommands WHERE command_id = %s", (command_id,)
                        )
                        current_config = cursor.fetchone()[0]

                        # Combine configurations
                        new_config = self._combine_configs(current_config, request_data)

                        # Update command
                        cursor.execute(update_query, (new_request_id, json.dumps(new_config), command_id))
                        conn.commit()

                        logger.info(f"Added request {new_request_id} to command {command_id}")

        except Exception as e:
            logger.error(f"Failed to add request {new_request_id} to command {command_id}: {e}")
            raise

    def _create_new_profiling_command(self, hostname: str, service_name: str, request_ids: List[str]):
        """Create a new profiling command"""
        command_id = str(uuid.uuid4())

        # Get request details to create combined config
        config = self._create_combined_config(request_ids)

        query = """
            INSERT INTO ProfilingCommands (
                command_id, hostname, service_name, combined_config, request_ids
            ) VALUES (%s, %s, %s, %s, %s)
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (command_id, hostname, service_name, json.dumps(config), request_ids))
                    conn.commit()
                    logger.info(f"Created new profiling command {command_id} for host {hostname}")

        except Exception as e:
            logger.error(f"Failed to create profiling command for host {hostname}: {e}")
            raise

    def _create_combined_config(self, request_ids: List[str]) -> Dict[str, Any]:
        """Create combined configuration from multiple requests"""
        query = """
            SELECT duration, frequency, profiling_mode, pids, additional_args
            FROM ProfilingRequests
            WHERE request_id = ANY(%s)
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (request_ids,))
                    requests = cursor.fetchall()

                    return self._combine_multiple_configs(requests)

        except Exception as e:
            logger.error(f"Failed to create combined config for requests {request_ids}: {e}")
            raise

    def _combine_configs(self, current_config: Dict, new_request_data: tuple) -> Dict[str, Any]:
        """Combine current config with new request data"""
        duration, frequency, profiling_mode, pids, additional_args = new_request_data

        # Use the most restrictive/specific values
        combined = current_config.copy()

        # Duration: use the maximum
        if duration and duration > combined.get("duration", 0):
            combined["duration"] = duration

        # Frequency: use the maximum
        if frequency and frequency > combined.get("frequency", 0):
            combined["frequency"] = frequency

        # PIDs: combine lists
        if pids:
            existing_pids = combined.get("pids", [])
            combined["pids"] = list(set(existing_pids + pids))

        # Additional args: merge
        if additional_args:
            combined["additional_args"] = {**combined.get("additional_args", {}), **additional_args}

        return combined

    def _combine_multiple_configs(self, requests) -> Dict[str, Any]:
        """Combine multiple request configurations"""
        combined = {"duration": 60, "frequency": 11, "profiling_mode": "cpu", "pids": [], "additional_args": {}}

        for duration, frequency, profiling_mode, pids, additional_args in requests:
            if duration and duration > combined["duration"]:
                combined["duration"] = duration

            if frequency and frequency > combined["frequency"]:
                combined["frequency"] = frequency

            if pids:
                existing_pids = combined.get("pids", [])
                combined["pids"] = existing_pids + pids

            if additional_args:
                if "additional_args" not in combined:
                    combined["additional_args"] = {}
                combined["additional_args"].update(additional_args)  # type: ignore[attr-defined]

        # Remove duplicates from PIDs
        combined["pids"] = list(set(combined["pids"]))  # type: ignore[arg-type]

        return combined

    def get_pending_profiling_command(
        self, hostname: str, service_name: str, exclude_command_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get pending profiling command for a host"""
        query = """
            SELECT command_id, combined_config, request_ids
            FROM ProfilingCommands
            WHERE hostname = %s
            AND service_name = %s
            AND status = 'pending'
        """
        params = [hostname, service_name]

        if exclude_command_id:
            query += " AND command_id != %s"
            params.append(exclude_command_id)

        query += " ORDER BY created_at ASC LIMIT 1"

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    result = cursor.fetchone()

                    if result:
                        return {"command_id": result[0], "combined_config": result[1], "request_ids": result[2]}
                    return None

        except Exception as e:
            logger.error(f"Failed to get pending command for {hostname}: {e}")
            return None

    def mark_profiling_command_sent(self, command_id: str, hostname: str):
        """Mark a profiling command as sent"""
        query = """
            UPDATE ProfilingCommands
            SET status = 'sent', sent_at = CURRENT_TIMESTAMP
            WHERE command_id = %s AND hostname = %s
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (command_id, hostname))
                    conn.commit()
                    logger.info(f"Marked command {command_id} as sent to {hostname}")

        except Exception as e:
            logger.error(f"Failed to mark command {command_id} as sent: {e}")
            raise

    def update_host_heartbeat(
        self,
        hostname: str,
        ip_address: str,
        service_name: str,
        status: str,
        last_command_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ):
        """Update host heartbeat information"""
        query = """
            INSERT INTO HostHeartbeats (hostname, ip_address, service_name, status, last_command_id, heartbeat_timestamp)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (hostname, service_name)
            DO UPDATE SET
                ip_address = EXCLUDED.ip_address,
                status = EXCLUDED.status,
                last_command_id = EXCLUDED.last_command_id,
                heartbeat_timestamp = EXCLUDED.heartbeat_timestamp,
                updated_at = CURRENT_TIMESTAMP
        """

        if timestamp is None:
            timestamp = datetime.now()

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (hostname, ip_address, service_name, status, last_command_id, timestamp))
                    conn.commit()
                    logger.debug(f"Updated heartbeat for {hostname}")

        except Exception as e:
            logger.error(f"Failed to update heartbeat for {hostname}: {e}")
            raise

    def update_profiling_command_status(
        self,
        command_id: str,
        hostname: str,
        status: str,
        execution_time: Optional[int] = None,
        error_message: Optional[str] = None,
        results_path: Optional[str] = None,
    ):
        """Update profiling command completion status"""
        query = """
            UPDATE ProfilingCommands
            SET status = %s,
                completed_at = CURRENT_TIMESTAMP,
                execution_time = %s,
                error_message = %s,
                results_path = %s
            WHERE command_id = %s AND hostname = %s
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (status, execution_time, error_message, results_path, command_id, hostname))

                    # Also update related profiling requests
                    if status == "completed":
                        self._mark_requests_completed(command_id)
                    elif status == "failed":
                        self._mark_requests_failed(command_id, error_message)

                    conn.commit()
                    logger.info(f"Updated command {command_id} status to {status}")

        except Exception as e:
            logger.error(f"Failed to update command {command_id} status: {e}")
            raise

    def _mark_requests_completed(self, command_id: str):
        """Mark all requests in a command as completed"""
        query = """
            UPDATE ProfilingRequests
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE request_id = ANY(
                SELECT unnest(request_ids) FROM ProfilingCommands WHERE command_id = %s
            )
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (command_id,))
                    conn.commit()

        except Exception as e:
            logger.error(f"Failed to mark requests completed for command {command_id}: {e}")

    def _mark_requests_failed(self, command_id: str, error_message: Optional[str]):
        """Mark all requests in a command as failed"""
        query = """
            UPDATE ProfilingRequests
            SET status = 'failed', error_message = %s, completed_at = CURRENT_TIMESTAMP
            WHERE request_id = ANY(
                SELECT unnest(request_ids) FROM ProfilingCommands WHERE command_id = %s
            )
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (error_message, command_id))
                    conn.commit()

        except Exception as e:
            logger.error(f"Failed to mark requests failed for command {command_id}: {e}")
