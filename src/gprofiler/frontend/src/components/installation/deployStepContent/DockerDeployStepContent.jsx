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

import { Box, Typography } from '@mui/material';
import { isEmpty } from 'lodash';
import { useState } from 'react';

import CopyableParagraph from '@/components/common/dataDisplay/CopyableParagraph';
import Flexbox from '@/components/common/layout/Flexbox';
import InstallationCheckBox from '@/components/installation/InstallationCheckBox';
import { getServerHostFlag } from '@/utils/installationUtils';

const DockerDeployStepContent = ({ apiKey, serviceName, serverHost }) => {
    const [shouldAddNoVerify, setShouldAddNoVerify] = useState(true);

    const staticCommand = `docker pull intel/gprofiler:latest\ndocker run --name granulate-gprofiler --restart=always -d --pid=host --userns=host --privileged intel/gprofiler:latest -cu --token="${apiKey}" --service-name="${serviceName}" ${getServerHostFlag(
        serverHost
    )}${shouldAddNoVerify ? ' --no-verify' : ''}`;

    const dynamicCommand = `docker pull intel/gprofiler:latest\ndocker run --name granulate-gprofiler --restart=always -d --pid=host --userns=host --privileged intel/gprofiler:latest -u --token="${apiKey}" --service-name="${serviceName}" ${getServerHostFlag(
        serverHost
    )} --enable-heartbeat-server --api-server "${serverHost || 'https://your-server'}" --heartbeat-interval 30${
        shouldAddNoVerify ? ' --no-verify' : ''
    }`;

    const isParagraphDisabled = isEmpty(serviceName);

    return (
        <p className='content-paragraph'>
            <Flexbox column spacing={3}>
                <InstallationCheckBox
                    enableText={'Include skip verification flag for SSL certificate'}
                    isChecked={shouldAddNoVerify}
                    setIsChecked={setShouldAddNoVerify}
                />
                <Box>
                    <Typography variant='body2' sx={{ mb: 1, fontWeight: 500 }}>
                        Static Mode
                    </Typography>
                    <Typography variant='caption' color='text.secondary' sx={{ display: 'block', mb: 2 }}>
                        Continuous profiling with fixed configuration set at launch
                    </Typography>
                    <CopyableParagraph disabled={isParagraphDisabled} isCode highlightedButton text={staticCommand} />
                </Box>
                <Box>
                    <Typography variant='body2' sx={{ mb: 1, fontWeight: 500 }}>
                        Dynamic Mode
                    </Typography>
                    <Typography variant='caption' color='text.secondary' sx={{ display: 'block', mb: 2 }}>
                        Continuous profiling with runtime-adjustable configuration via web UI
                    </Typography>
                    <CopyableParagraph disabled={isParagraphDisabled} isCode highlightedButton text={dynamicCommand} />
                </Box>
            </Flexbox>
        </p>
    );
};

export default DockerDeployStepContent;
