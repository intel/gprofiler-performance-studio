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

export const PAGES = {
    profiles: {
        key: 'profiles',
        label: 'Profiles',
        to: '/profiles',
    },
    overview: {
        key: 'overview',
        label: 'Overview',
        to: '/overview',
    },
    comparison: {
        key: 'comparison',
        label: 'Comparison',
        to: '/compare',
    },
    installation: {
        key: 'installation',
        label: 'Install Service',
        to: '/installation',
    },
    welcome: {
        key: 'welcome',
        label: 'Welcome',
        to: '/welcome',
    },
    login: {
        key: 'login',
        label: 'Login',
        to: '/login',
    },
    profiling: {
        key: 'profiling',
        label: 'Dynamic Profiling',
        to: '/profiling',
    },
};

export const EXTERNAL_URLS = {
    documentation: {
        key: 'documentation',
        label: 'documentation',
        to: 'https://docs.gprofiler.io/',
    },
    github: {
        key: 'github',
        label: 'github',
        to: 'https://github.com/intel/gprofiler',
    },
    flameGraphLearn: {
        key: 'flameGraphLearn',
        label: 'learn more',
        to: 'https://docs.gprofiler.io/about-gprofiler/gprofiler-features/views/flame-graph',
    },
    tableViewLearn: {
        key: 'tableViewLearn',
        label: 'learn more',
        to: 'https://docs.gprofiler.io/about-gprofiler/gprofiler-features/views/table-view',
    },
    serviceViewLearn: {
        key: 'serviceViewLearn',
        label: 'learn more',
        to: 'https://docs.gprofiler.io/about-gprofiler/gprofiler-features/views/service-overview',
    },
};

export const PROFILES_VIEWS = {
    flamegraph: 'flamegraph',
    table: 'table',
    service: 'service',
    html: 'html',
};

export const SPLIT_VIEW_ANIMATION_DURATION_IN_SECONDS = 0.7;

export const COPY_ONLY_IN_HTTPS = 'This feature is available only in secure contexts (HTTPS)';
export const STACKS_COUNT = 500000;
export const ENV_VAR_PREFIX = import.meta.env;
export const DEMO_URL = 'https://demo-profiler.granulate.io/';
