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

import Box from '@mui/material/Box';
import { useContext } from 'react';
import { ErrorBoundary } from 'react-error-boundary';

import { FgContext } from '../../states';
import { SelectorsContext } from '../../states';
import { FgHoverContextProvider } from '../../states/flamegraph/FgHoverContext';
import { PROFILES_VIEWS } from '../../utils/consts';
import { useFullScreenContext } from '../../utils/contexts';
import ErrorFallback from '../common/feedback/ErrorFallback';
import ProfilesViews from './ProfilesViews';
import FgTooltip from './views/flamegraph/FgTooltip';
import LegendBoxContainer from './views/legendBox/LegendBoxContainer';

const ProfilesViewsWrapper = () => {
    const { isFgDisplayed } = useContext(FgContext);
    const { isFullScreen } = useFullScreenContext();

    const { viewMode } = useContext(SelectorsContext);
    const isTableView = viewMode === PROFILES_VIEWS.table;
    const isFlameGraphView = viewMode === PROFILES_VIEWS.flamegraph;
    const isAdhocView = viewMode === PROFILES_VIEWS.adhoc;
    // Adhoc view doesn't depend on flamegraph data
    const shouldDisplayView = isFgDisplayed || isAdhocView;
    return (
        <FgHoverContextProvider>
            <ErrorBoundary FallbackComponent={ErrorFallback}>
                <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', alignItems: 'stretch' }}>
                    <Box sx={{ p: isTableView ? 0 : 4, height: '100%' }}>
                        <div
                            style={{
                                display: shouldDisplayView ? 'inherit' : 'none',
                                overflow: 'hidden',
                                width: '100%',
                                height: isFullScreen ? '90vh' : isFlameGraphView ? 'calc(100vh - 200px)' : 'auto',
                                maxHeight: isFullScreen ? '90vh' : isFlameGraphView ? 'calc(100vh - 200px)' : 'auto',
                            }}>
                            {shouldDisplayView && <ProfilesViews />}
                        </div>
                        {isFlameGraphView && (
                            <Box
                                sx={{
                                    position: 'absolute',
                                    bottom: '15px',
                                    px: 4,
                                    py: 0,
                                    backgroundColor: 'white.main',
                                    boxShadow: 3,
                                    borderRadius: 2,
                                }}>
                                <LegendBoxContainer />
                            </Box>
                        )}
                        <FgTooltip />
                    </Box>
                </Box>
            </ErrorBoundary>
        </FgHoverContextProvider>
    );
};

export default ProfilesViewsWrapper;
