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

import ProfilingStatusPage from '../components/console/ProfilingStatusPage';
import InstallationPage from '../components/installation/InstallationPage';
import OverviewPage from '../components/overview/OverviewPage';
import WelcomePage from '../components/welcome/WelcomePage';
import { PAGES } from '../utils/consts';

export const ROUTES = [
    { path: PAGES.overview.to, exact: false, component: <OverviewPage /> },
    { path: PAGES.welcome.to, exact: true, component: <WelcomePage /> },
    { path: PAGES.installation.to, exact: false, component: <InstallationPage /> },
    { path: PAGES.profiling.to, exact: false, component: <ProfilingStatusPage /> },
];
