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
import { memo, useCallback, useContext, useEffect, useState } from 'react';

import { useGetServiceExtMetricGraph, useGetServiceExtMetricNames } from '@/api/hooks/useGetServiceExtMetrics';
import useGetServiceMemoryAndCpu from '@/api/hooks/useGetServiceMemoryAndCpu';
import useGetServiceNodesAndCores from '@/api/hooks/useGetServiceNodesAndCores';
import useGetServiceSamples from '@/api/hooks/useGetServiceSamples';
import Flexbox from '@/components/common/layout/Flexbox';
import Select from '@/components/common/selectors/select/Select';
import ResoultionDropDown from '@/components/profiles/views/service/ResolutionDropDown';
import { SelectorsContext } from '@/states';

import CoresGraph from './graphs/CoresGraph';
import CpuGraph from './graphs/CpuGraph';
import ExtMetricGraph from './graphs/ExtMetricGraph';
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

    const { memoryAndCpuData, memoryAndCpuLoading } = useGetServiceMemoryAndCpu({ resolution: resolutionValue });
    const { nodesAndCoresData, nodesAndCoresLoading } = useGetServiceNodesAndCores({
        resolution: resolutionValue,
    });

    const { extNames, extNamesLoading } = useGetServiceExtMetricNames();
    const [extName, setExtName] = useState(undefined);
    // Fall back to the first name until one is picked, or when the pick isn't in the current range/filter.
    const selectedExtName = extNames?.includes(extName) ? extName : extNames?.[0];
    const { extGraphData, extGraphLoading } = useGetServiceExtMetricGraph({
        resolution: resolutionValue,
        name: selectedExtName,
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

    return (
        <Box sx={{ backgroundColor: 'fieldBlue.main', p: 8, pt: 6, borderRadius: 2, height: '340px' }}>
            <TabContext value={selectedGraphTab}>
                <Flexbox column={false} justifyContent={'space-between'} alignItems={'flex-start'}>
                    <Box sx={{ borderBottom: 1, borderColor: 'divider', width: '490px', mb: 8 }}>
                        <StyledTabs onChange={changeTab}>
                            <StyledTab label='CPU' value='1' />
                            <StyledTab label='MEMORY' value='2' />
                            <StyledTab label='SAMPLES' value='3' />
                            <StyledTab label='NODES' value='4' />
                            <StyledTab label='CORES' value='5' />
                            <StyledTab label='ADDITIONAL' value='6' />
                        </StyledTabs>
                    </Box>
                    <Flexbox alignItems={'center'}>
                        {selectedGraphTab === '6' && extNames?.length > 0 && (
                            <Flexbox alignItems={'center'} sx={{ width: '220px', mr: 6 }}>
                                <Typography sx={{ mr: 2 }}>Metric:</Typography>
                                <Select
                                    fullWidth={true}
                                    placeholder='Metric'
                                    selectedOption={selectedExtName}
                                    onSelect={setExtName}
                                    options={extNames}
                                />
                            </Flexbox>
                        )}
                        <Flexbox alignItems={'center'} sx={{ width: '200px' }}>
                            <Typography sx={{ mr: 2 }}>Resolution:</Typography>
                            <ResoultionDropDown
                                setResolutionValue={setResolutionValue}
                                setResolution={setResolution}
                                resolution={resolution}
                            />
                        </Flexbox>
                    </Flexbox>
                </Flexbox>
                <StyledTabPanel value='1'>
                    {memoryAndCpuLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <CpuGraph data={memoryAndCpuData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
                <StyledTabPanel value='2'>
                    {memoryAndCpuLoading ? (
                        <GraphSkeleton />
                    ) : (
                        <MemoryGraph data={memoryAndCpuData} edges={edges} setZoomedTime={setZoomedTime} />
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
                    {extNamesLoading || extGraphLoading ? (
                        <GraphSkeleton />
                    ) : !extNames?.length ? (
                        <Flexbox justifyContent={'center'} alignItems={'center'} sx={{ height: '100%' }}>
                            <Typography>No additional metrics for this service</Typography>
                        </Flexbox>
                    ) : (
                        <ExtMetricGraph data={extGraphData} edges={edges} setZoomedTime={setZoomedTime} />
                    )}
                </StyledTabPanel>
            </TabContext>
        </Box>
    );
});
ServiceGraph.displayName = 'ServiceGraph';
export default ServiceGraph;
