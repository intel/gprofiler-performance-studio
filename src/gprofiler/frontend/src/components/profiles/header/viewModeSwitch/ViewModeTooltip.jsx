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

import { Typography } from '@mui/material';

import Button from '@/components/common/button/Button';
import Tooltip from '@/components/common/dataDisplay/muiToolTip/Tooltip';
import { ICONS_NAMES } from '@/components/common/icon/iconsData';
import Flexbox from '@/components/common/layout/Flexbox';
import { EXTERNAL_URLS, PROFILES_VIEWS } from '@/utils/consts';

const viewModes = {
    [PROFILES_VIEWS.flamegraph]: {
        label: 'Flame Graph',
        description: 'Visual representation of hierarchical data, created to visualize stack traces of profiled data',
        infoURL: EXTERNAL_URLS.flameGraphLearn.to,
        icon: ICONS_NAMES.FlameGraphView,
    },
    [PROFILES_VIEWS.table]: {
        label: 'Table view',
        description: 'Table view are a tabular representation of the profiling data aggregated by function calls',
        infoURL: EXTERNAL_URLS.tableViewLearn.to,
        icon: ICONS_NAMES.TableView,
    },
    [PROFILES_VIEWS.service]: {
        label: 'Service overview',
        description: 'An overview of your gProfiler service, showing the service metrics and more',
        infoURL: EXTERNAL_URLS.serviceViewLearn.to,
        icon: ICONS_NAMES.ServiceView,
    },
    [PROFILES_VIEWS.html]: {
        label: 'Last HTML view',
        description: 'The latest HTML of your gProfiler service and hostname',
        icon: ICONS_NAMES.LastHtmlView,
    },
    [PROFILES_VIEWS.adhoc]: {
        label: 'Adhoc profiling',
        description: 'Browse and view pre-generated flamegraph HTML files from S3 storage',
        icon: ICONS_NAMES.FlameGraphView,
    },
};

const TooltipContent = ({ viewMode }) => {
    const { label, description, infoURL } = viewModes[viewMode || PROFILES_VIEWS.flamegraph];
    return (
        <Flexbox column spacing={4} justifyContent='start'>
            <Typography variant='subtitle2_lato'>{label}</Typography>

            <Typography variant='body4_lato'>{description}</Typography>

            {!!infoURL && (
                <Button href={infoURL} fullWidth>
                    Learn more
                </Button>
            )}
        </Flexbox>
    );
};

const ViewModeTooltip = ({ viewMode, children }) => {
    return (
        <Tooltip variant='dark' title={viewMode ? <TooltipContent viewMode={viewMode} /> : ''} placement='left' arrow>
            {children}
        </Tooltip>
    );
};

export default ViewModeTooltip;
