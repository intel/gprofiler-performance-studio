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

import TabContext from '@mui/lab/TabContext';
import { Box } from '@mui/material';
import Typography from '@mui/material/Typography';
import { memo, useCallback, useContext, useState } from 'react';

import useGetServiceMetrics from '@/api/hooks/useGetServiceMetrics';
import useGetServiceNodesAndCores from '@/api/hooks/useGetServiceNodesAndCores';
import useGetServiceSamples from '@/api/hooks/useGetServiceSamples';
import Flexbox from '@/components/common/layout/Flexbox';
import CpiCountGraph from '@/components/profiles/views/service/graphs/CpiCountGraph';
import ResoultionDropDown from '@/components/profiles/views/service/ResolutionDropDown';
import TmaBackendBoundGraph from '@/components/profiles/views/service/graphs/TmaBackendBoundGraph';
import TmaBadSpecGraph from '@/components/profiles/views/service/graphs/TmaBadSpecGraph';
import TmaFrontEndBoundGraph from '@/components/profiles/views/service/graphs/TmaFrontEndBoundGraph';
import TmaRetiringGraph from '@/components/profiles/views/service/graphs/TmaRetiringGraph';
import FrequencyGraph from '@/components/profiles/views/service/graphs/FrequencyGraph';
import { SelectorsContext } from '@/states';

import CoresGraph from './graphs/CoresGraph';
import CpuGraph from './graphs/CpuGraph';
import GraphSkeleton from './graphs/GraphSkeleton';
import { useGetEdgesTimes } from './graphs/graphUtils';
import MemoryGraph from './graphs/MemoryGraph';
import NodesGraph from './graphs/NodesGraph';
import SamplesGraph from './graphs/SamplesGraph';
import { StyledTab, StyledTabPanel, StyledTabs } from './serviceGraph.styles';

const ServiceGraph = memo(() => {
    const [currentTab, setTab] = useState('1');
    const [resolution, setResolution] = useState('');
    const [resolutionValue, setResolutionValue] = useState('');

    const { samplesData, samplesLoading } = useGetServiceSamples({ resolution: resolutionValue });

    const { metricsData, metricsLoading } = useGetServiceMetrics({ resolution: resolutionValue });
    const { nodesAndCoresData, nodesAndCoresLoading } = useGetServiceNodesAndCores({
        resolution: resolutionValue,
    });
    const { edges } = useGetEdgesTimes();

    const { setTimeSelection, selectedGraphTab, setSelectedGraphTab } = useContext(SelectorsContext);
    const setZoomedTime = useCallback(
        ({ chart }) => {
            const firstTick = chart.scales.x.ticks[0];
            const lastTick = chart.scales.x.ticks[chart.scales.x.ticks.length - 1];
            const startTime = new Date(firstTick.value);
            const endTime = new Date(lastTick.value);
            setTimeSelection({ customTime: { startTime, endTime } });
        },
        [setTimeSelection]
    );

    const changeTab = (event, newTab) => {
        setSelectedGraphTab(newTab);
    };
    const isTmaFrontEndBoundExist = !!metricsData?.find((metric) => (metric?.avg_tma_front_end_bound || metric?.max_tma_front_end_bound));
    const isTmaBackendBoundExist = !!metricsData?.find((metric) => (metric?.avg_tma_backend_bound || metric?.max_tma_backend_bound));
    const isTmaBadSpecExist = !!metricsData?.find((metric) => (metric?.avg_tma_bad_spec || metric?.max_tma_bad_spec));
    const isTmaRetiringExist = !!metricsData?.find((metric) => (metric?.avg_tma_retiring || metric?.max_tma_retiring));
    const isCpiCountExist = !!metricsData?.find((metric) => (metric?.avg_cpi_count || metric?.max_cpi_count));
    const isFrequencyExist = !!metricsData?.find((metric) => (metric?.avg_frequency || metric?.max_frequency));
    return (
        <Box sx={{ backgroundColor: 'fieldBlue.main', p: 8, pt: 6, borderRadius: 2, height: '340px' }}>
            <TabContext value={selectedGraphTab}>
                <Flexbox column={false} justifyContent={'space-between'} alignItems={'flex-start'}>
                    <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 8 }}>
                        <StyledTabs onChange={changeTab}>
                            <StyledTab label='CPU' value='1' />
                            <StyledTab label='MEMORY' value='2' />
                            <StyledTab label='SAMPLES' value='3' />
                            <StyledTab label='NODES' value='4' />
                            <StyledTab label='CORES' value='5' />
                            {isTmaFrontEndBoundExist && <StyledTab label='TMA FRONT END BOUND' value='6' />}
                            {isTmaBackendBoundExist && <StyledTab label='TMA BACKEND BOUND' value='7' />}
                            {isTmaBadSpecExist && <StyledTab label='TMA BAD SPEC' value='8' />}
                            {isTmaRetiringExist && <StyledTab label='TMA RETIRING' value='9' />}
                            {isCpiCountExist && <StyledTab label='CPI COUNT' value='10' />}
                            {isFrequencyExist && <StyledTab label='FREQUENCY' value='11' />}
                        </StyledTabs>
                    </Box>
                    <Flexbox alignItems={'center'} sx={{ width: '200px' }}>
                        <Typography sx={{ mr: 2 }}>Resolution:</Typography>
                        <ResoultionDropDown
                            setResolutionValue={setResolutionValue}
                            setResolution={setResolution}
                            resolution={resolution}
                        />
                    </Flexbox>
                </Flexbox>
                <StyledTabPanel value='1'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <CpuGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='2'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <MemoryGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='3'>
                    {samplesLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <SamplesGraph data={samplesData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='4'>
                    {nodesAndCoresLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <NodesGraph data={nodesAndCoresData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='5'>
                    {nodesAndCoresLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <CoresGraph data={nodesAndCoresData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='6'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <TmaFrontEndBoundGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='7'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <TmaBackendBoundGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='8'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <TmaBadSpecGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='9'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <TmaRetiringGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='10'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <CpiCountGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='11'>
                    {metricsLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <FrequencyGraph data={metricsData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
            </TabContext>
        </Box>
    );
});
ServiceGraph.displayName = 'ServiceGraph';
export default ServiceGraph;
