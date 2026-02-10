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

import { Box } from '@mui/material';
import { useMemo, useState } from 'react';

import useGetTableFunctionCpuData from '@/api/hooks/useGetTableFunctionCpuData';
import Button from '@/components/common/button/Button';
import { TabPanel, Tabs } from '@/components/common/dataDisplay/tabs/Tabs';
import Icon from '@/components/common/icon/Icon';
import { ICONS_NAMES } from '@/components/common/icon/iconsData';
import Flexbox from '@/components/common/layout/Flexbox';
import FunctionCpuGraph from '@/components/profiles/views/service/graphs/FunctionCpuGraph';
import { SplitViewFgHoverContext, SplitViewFgHoverContextProvider } from '@/states/flamegraph/SplitViewFgHoverContext';
import { COLORS } from '@/theme/colors';
import { SPLIT_VIEW_ANIMATION_DURATION_IN_SECONDS } from '@/utils/consts';
import { getCalledByFlameGraph, getCallsFlameGraph } from '@/utils/splitViewUtils';

import FgTooltip from '../flamegraph/FgTooltip';
import { parseFlamegraphData } from '../flamegraph/parsingUtils';
import { FunctionFlamegraph } from './FunctionFlamegraph';

export const SplitViewDivider = ({ setRowSelected }) => {
    return (
        <Flexbox
            alignItems='center'
            justifyContent='center'
            sx={{
                backgroundColor: 'grey.main',
                position: 'relative',
                marginLeft: '-6px',
                width: '12px',
                overflow: 'visible',
            }}>
            <Button
                iconOnly
                sxOverrides={{
                    position: 'absolute',
                    bottom: 5,
                    left: 3,
                    backgroundColor: 'grey.main',
                    borderRadius: '0px 15px 15px 0px',
                    py: 0,
                    pl: 1,
                    '&:hover': {
                        backgroundColor: 'grey.main',
                    },
                }}
                onClick={() => {
                    setRowSelected(undefined);
                }}>
                <Icon
                    name={ICONS_NAMES.ChevronDoubleRight}
                    color={COLORS.WHITE}
                    hoverColor={COLORS.SECONDARY_ORANGE}
                    size={22}
                />
            </Button>
        </Flexbox>
    );
};

const getSplitViewCallsFG = (callsData) => {
    const callsFlamegraph = getCallsFlameGraph(callsData);
    return [parseFlamegraphData(callsFlamegraph, 0, 0, true, false, [], false)];
};

const getSplitViewParsedCalledByFG = (calledByData, tableMappingData) => {
    const callsFlamegraph = getCalledByFlameGraph(calledByData, tableMappingData);
    return [parseFlamegraphData(callsFlamegraph, 0, 0, true, false, [], false)];
};

export const SplitView = ({ fgData, width, height, tableMappingData }) => {
    const [splitViewTab, setSplitViewTab] = useState(1);
    const callsFgData = useMemo(() => getSplitViewCallsFG(fgData), [fgData]);

    const { functionCpuData, functionCpuLoading } = useGetTableFunctionCpuData({
        functionName: (fgData?.function ? fgData.function : '') + (fgData?.suffix ? fgData.suffix : ''),
    });

    const calledByFgData = useMemo(
        () => getSplitViewParsedCalledByFG(fgData, tableMappingData),

        [fgData, tableMappingData]
    );

    return (
        <SplitViewFgHoverContextProvider>
            <Flexbox column>
                <Box sx={{ width: '100%' }}>
                    <Tabs
                        splitViewTab={splitViewTab}
                        setSplitViewTab={setSplitViewTab}
                        tabs={['Called by', 'Calls', 'Total CPU']}
                        containerPaintDurationInSeconds={SPLIT_VIEW_ANIMATION_DURATION_IN_SECONDS * 0.8}
                    />
                </Box>

                <TabPanel value={splitViewTab} index={0} style={{ height: height + 'px' }}>
                    {calledByFgData && (
                        <FunctionFlamegraph flameGraphData={calledByFgData} width={width} height={height} inverted />
                    )}
                </TabPanel>
                <TabPanel value={splitViewTab} index={1} style={{ height: height + 'px' }}>
                    {callsFgData && <FunctionFlamegraph flameGraphData={callsFgData} width={width} height={height} />}
                </TabPanel>
                <TabPanel value={splitViewTab} index={2} style={{ height: height + 'px' }}>
                    <Flexbox sx={{ height: '100%' }} alignItems='center'>
                        <Flexbox sx={{ width: width, p: 4, height: '80%' }}>
                            <FunctionCpuGraph
                                functionCpuData={functionCpuData}
                                functionCpuLoading={functionCpuLoading}
                            />
                        </Flexbox>
                    </Flexbox>
                </TabPanel>
            </Flexbox>
            {splitViewTab < 2 && <FgTooltip ctx={SplitViewFgHoverContext} />}
        </SplitViewFgHoverContextProvider>
    );
};
