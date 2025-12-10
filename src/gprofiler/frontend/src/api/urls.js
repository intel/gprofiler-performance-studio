{
    /*
     * Copyright (C) 2023 Intel Corporation
     *
     * Licensed under the Apache License, Version 2.0 (the "License");
     * you may not use this file except in compliance with the License.
     * You may obtain a copy of the License at
     *
     *    http://www.apache.org/licenses/LICENSE-2.0
     *
     * Unless required by applicable law or agreed to in writing, software
     * distributed under the License is distributed on an "AS IS" BASIS,
     * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
     * See the License for the specific language governing permissions and
     * limitations under the License.
     */
}

import { stringify } from 'query-string';

const API_PREFIX = '/api';
const FILETERS_PREFIX = '/v1/filters';

export const DATA_URLS = {
    INSTALLATION_DAEMON: `${API_PREFIX}/installations/daemon_set/file?`,
    GET_SERVICES_SUMMARY: `${API_PREFIX}/overview`,
    GET_SERVICES_DATA: `${API_PREFIX}/overview/services`,
    GET_SERVICES_LIST: `${API_PREFIX}/services`,
    GET_FLAMEGRAPH: `${API_PREFIX}/flamegraph`,
    DOWNLOAD_FLAMEGRAPH: `${API_PREFIX}/flamegraph/download_`,
    GET_FLAMEGRAPH_DATETIME_WITH_DATA: `${API_PREFIX}/flamegraph/datetime_with_data`,
    GET_METRICS: `${API_PREFIX}/metrics/summary`,
    GET_METRICS_CPU_AND_MEMORY_TREND: `${API_PREFIX}/metrics/cpu_trend`,
    GET_NODES_AND_CORES: `${API_PREFIX}/metrics/nodes_cores/summary`,
    GET_LAST_HTML: `${API_PREFIX}/metrics/html_metadata`,
    GET_INSTANCE_TYPE: `${API_PREFIX}/metrics/instance_type_count`,
    GET_GRAPH_METRICS: `${API_PREFIX}/metrics/graph`,
    GET_FUCNTION_CPU_GRAPH: `${API_PREFIX}/metrics/function_cpu`,
    GET_NODES_AND_CORES_GRAPH_METRICS: `${API_PREFIX}/metrics/graph/nodes_and_cores`,
    GET_SAMPLES: `${API_PREFIX}/metrics/samples`,
    GET_API_KEY: `${API_PREFIX}/api_key`,
    // Profiling endpoints
    GET_PROFILING_HOST_STATUS: `${API_PREFIX}/metrics/profiling/host_status`,
    POST_PROFILING_REQUEST: `${API_PREFIX}/metrics/profile_request`,
    POST_HEARTBEAT: `${API_PREFIX}/metrics/heartbeat`,
    POST_COMMAND_COMPLETION: `${API_PREFIX}/metrics/command_completion`,
    // Filter endpoints
    FILTERS: `${API_PREFIX}${FILETERS_PREFIX}`,
    GET_FILTER_OPTIONS_VALUE: (filterType, params) =>
        `${API_PREFIX}${FILETERS_PREFIX}/tags/${filterType}?${stringify(params)}`,
    GET_FILTERS_FOR_SERVICE: (selectedService) => `${API_PREFIX}${FILETERS_PREFIX}/service/${selectedService}`,
    SNAPSHOT: `${API_PREFIX}/snapshots`,
};
