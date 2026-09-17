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
Utility functions for PMU (Performance Monitoring Unit) event handling.
"""

# Perf event name normalization mapping
# Maps UI event names (e.g., 'cpu-cycles') to agent-normalized names (e.g., 'cycles')
PERF_EVENT_NORMALIZATION_MAP = {
    "cpu-cycles": "cycles",
    "cpu-instructions": "instructions",
    "cpu-cache-misses": "cache-misses",
    "cpu-cache-references": "cache-references",
    "cpu-branch-instructions": "branch-instructions",
    "cpu-branch-misses": "branch-misses",
    "cpu-stalled-cycles-frontend": "stalled-cycles-frontend",
    "cpu-stalled-cycles-backend": "stalled-cycles-backend",
}


def normalize_perf_event_name(event: str) -> str:
    """
    Normalize perf event names to match what the agent stores.
    
    The agent normalizes events like 'cpu-cycles' -> 'cycles', 
    'cpu/cache-misses/' -> 'cache-misses'
    
    Args:
        event: Event name from UI or user input (e.g., 'cpu-cycles')
        
    Returns:
        Normalized event name (e.g., 'cycles')
        
    Example:
        >>> normalize_perf_event_name('cpu-cycles')
        'cycles'
        >>> normalize_perf_event_name('cpu/cache-misses/')
        'cache-misses'
        >>> normalize_perf_event_name('cycles')
        'cycles'
    """
    # Remove cpu/ prefix and trailing slash if present
    event = event.replace("cpu/", "").replace("/", "")
    
    # Apply normalization mapping
    return PERF_EVENT_NORMALIZATION_MAP.get(event, event)
