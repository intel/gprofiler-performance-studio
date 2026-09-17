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

from typing import List, Optional

import bitmath

from backend.config import MAX_SIMULTANEOUS_PROFILING_HOSTS_PERCENT, MAX_PROFILING_REQUEST_HOSTS
from backend.models.metrics_models import BulkProfilingRequest


def validate_profiling_capacity(
    bulk_profiling_request: BulkProfilingRequest,
    db_manager,
    service_name: Optional[str] = None
) -> tuple[bool, Optional[str], List[str]]:
    """
    Validate that the bulk profiling request doesn't exceed the maximum simultaneous profiling capacity.
    
    This function aggregates all target hosts across all requests in the bulk operation and validates
    the total capacity requirements.
    
    Args:
        bulk_profiling_request: The BulkProfilingRequest object containing multiple requests
        db_manager: Instance of DBManager to query active profiling hosts
        service_name: Optional service name to filter by (if None, checks globally)
        
    Returns:
        tuple: (is_valid: bool, error_message: Optional[str], target_hostnames: List[str])
            - is_valid: True if capacity check passes
            - error_message: Error description if validation fails
            - target_hostnames: List of all unique hostnames from all requests
        
    Example:
        >>> from gprofiler_dev.postgres.db_manager import DBManager
        >>> db_manager = DBManager()
        >>> is_valid, error, hostnames = validate_profiling_capacity(bulk_request, db_manager)
        >>> if not is_valid:
        ...     raise ValueError(error)
    """
    # Collect all target hostnames from all requests
    all_target_hostnames: List[str] = []
    has_start_requests = False
    
    for profiling_request in bulk_profiling_request.requests:
        # Track if there are any "start" requests
        if profiling_request.request_type == "start":
            has_start_requests = True
            
        # Collect all hostnames from target_hosts
        if profiling_request.target_hosts:
            all_target_hostnames.extend(profiling_request.target_hosts.keys())
    
    # Only validate capacity for bulk requests that contain "start" operations
    if not has_start_requests:
        return True, None, all_target_hostnames
    
    # Calculate total request size from all collected hostnames
    request_size = len(all_target_hostnames)
    
    # Validate that request size doesn't exceed MAX_PROFILING_REQUEST_HOSTS
    if request_size > MAX_PROFILING_REQUEST_HOSTS:
        error_msg = (
            f"Request size exceeded.\n"
            f"Request size: {request_size} hosts\n"
            f"Maximum allowed per request: {MAX_PROFILING_REQUEST_HOSTS} hosts\n"
            f"Please reduce the number of hosts in your request by {request_size - MAX_PROFILING_REQUEST_HOSTS} hosts."
        )
        return False, error_msg, all_target_hostnames
    
    # Get counts, excluding hosts from the current bulk request
    active_hosts_count = db_manager.get_active_hosts_count(service_name)
    currently_profiling_host_count = db_manager.get_actively_profiling_hosts_count(
        service_name=service_name,
    )
    currently_profiling_host_count_inside_selection = db_manager.get_actively_profiling_hosts_count(
        service_name=service_name,
        host_inclusion_list=all_target_hostnames
    )
    currently_profiling_host_count_outside_selection = db_manager.get_actively_profiling_hosts_count(
        service_name=service_name,
        host_exclusion_list=all_target_hostnames
    )
    
    # Calculate maximum allowed profiling hosts
    max_profiling_hosts = int((active_hosts_count * MAX_SIMULTANEOUS_PROFILING_HOSTS_PERCENT) / 100)
    
    # Calculate new total if this request is approved
    new_profiling_total = currently_profiling_host_count_outside_selection + request_size
    
    # Check if it would exceed the limit
    if new_profiling_total > max_profiling_hosts:
        error_msg = (
            f"Profiling capacity exceeded.\n"
            f"Currently profiling: {currently_profiling_host_count} hosts\n"
            f"Currently profiling inside selection: {currently_profiling_host_count_inside_selection} hosts\n"
            f"Currently profiling outside selection: {currently_profiling_host_count_outside_selection} hosts\n"
            f"Request size: {request_size} hosts\n"
            f"Active hosts: {active_hosts_count}\n"
            f"Maximum allowed ({MAX_SIMULTANEOUS_PROFILING_HOSTS_PERCENT}%): {max_profiling_hosts} hosts\n"
            f"This request would result in {new_profiling_total} profiling hosts, "
            f"which exceeds the limit by {new_profiling_total - max_profiling_hosts} hosts."
        )
        return False, error_msg, all_target_hostnames
    
    return True, None, all_target_hostnames


def validate_pmu_events(
    bulk_profiling_request: BulkProfilingRequest,
    db_manager
) -> tuple[bool, Optional[str]]:
    """
    Validate that all hosts in the bulk profiling request support the requested PMU events.
    
    This function validates PMU event support for all "start" requests with perf enabled.
    It checks each service's requested events against host capabilities stored in the database.
    
    Args:
        bulk_profiling_request: The BulkProfilingRequest object containing multiple requests
        db_manager: Instance of DBManager to query host PMU capabilities
        
    Returns:
        tuple: (is_valid: bool, error_message: Optional[str])
            - is_valid: True if all hosts support requested events
            - error_message: Combined error messages if validation fails for any service
        
    Example:
        >>> from gprofiler_dev.postgres.db_manager import DBManager
        >>> db_manager = DBManager()
        >>> is_valid, error = validate_pmu_events(bulk_request, db_manager)
        >>> if not is_valid:
        ...     raise ValueError(error)
    """
    pmu_validation_errors = []
    
    for profiling_request in bulk_profiling_request.requests:
        # Only validate "start" requests with additional_args
        if profiling_request.request_type == "start" and profiling_request.additional_args:
            profiler_configs = profiling_request.additional_args.get("profiler_configs", {})
            perf_config = profiler_configs.get("perf", {})
            perf_mode = perf_config.get("mode", "disabled")
            perf_events = perf_config.get("events", [])
            
            # Only validate if perf is enabled and events are specified
            if perf_mode != "disabled" and perf_events:
                # target_hosts is only populated for host-scope requests. For
                # workload scopes (service/namespace/pod/container/process) the
                # UI sends no target_hosts because the concrete hosts are
                # resolved later; fall back to None so events are validated
                # against all of the service's active hosts instead of crashing
                # on None.keys().
                target_hostnames_for_service = (
                    list(profiling_request.target_hosts.keys())
                    if profiling_request.target_hosts
                    else None
                )

                validation_result = db_manager.validate_perf_events_support(
                    service_name=profiling_request.service_name,
                    requested_events=perf_events,
                    target_hostnames=target_hostnames_for_service
                )
                
                if not validation_result["valid"]:
                    error_msg = validation_result["error_message"]
                    pmu_validation_errors.append(f"Service '{profiling_request.service_name}': {error_msg}")
    
    # If PMU validation failed for any service, return combined error
    if pmu_validation_errors:
        combined_error = "\n\n".join(pmu_validation_errors)
        return False, combined_error
    
    return True, None


_VALID_AP_TIME_MODES = frozenset({"cpu", "itimer", "wall", "auto", "alloc"})


def validate_async_profiler_config(bulk_profiling_request: BulkProfilingRequest) -> tuple[bool, Optional[str]]:
    """
    Validate the async_profiler config in each profiling request's additional_args.

    Checks that:
    - async_profiler.time is one of the supported modes
    - alloc_interval is a non-empty string when time == 'alloc'

    Returns:
        tuple: (is_valid: bool, error_message: Optional[str])
    """
    errors = []

    for profiling_request in bulk_profiling_request.requests:
        if profiling_request.request_type != "start" or not profiling_request.additional_args:
            continue

        profiler_configs = profiling_request.additional_args.get("profiler_configs", {})
        async_profiler_config = profiler_configs.get("async_profiler")
        if not isinstance(async_profiler_config, dict):
            continue

        if not async_profiler_config.get("enabled", True):
            continue

        time_mode = async_profiler_config.get("time", "cpu")
        if time_mode not in _VALID_AP_TIME_MODES:
            errors.append(
                f"Service '{profiling_request.service_name}': "
                f"Invalid async_profiler time mode {time_mode!r}. "
                f"Valid modes: {sorted(_VALID_AP_TIME_MODES)}"
            )
            continue

        if time_mode == "alloc":
            alloc_interval = async_profiler_config.get("alloc_interval", "")
            if not isinstance(alloc_interval, str) or not alloc_interval:
                errors.append(
                    f"Service '{profiling_request.service_name}': "
                    f"Invalid alloc_interval value {alloc_interval!r}: "
                    "must be a non-empty string (e.g. '2MB', '512KiB')"
                )
                continue
            try:
                bitmath.parse_string(alloc_interval)
            except ValueError:
                errors.append(
                    f"Service '{profiling_request.service_name}': "
                    f"Could not parse alloc_interval {alloc_interval!r}: "
                    "must be a number followed by a size unit (e.g. '2MB', '512KiB')"
                )

    if errors:
        return False, "\n\n".join(errors)

    return True, None
