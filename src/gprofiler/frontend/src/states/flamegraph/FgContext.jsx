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

import { createContext, useContext, useEffect, useState } from 'react';

import useTruncationQueryParams from '@/hooks/useTruncationQueryParams';
import { SelectorsContext } from '@/states/selectors';

export const FgContext = createContext();

export const FgProvider = ({ children }) => {
    const { timeSelection } = useContext(SelectorsContext);

    // Use State to keep the values
    const [lastWeekOriginData, setLastWeekOriginData] = useState({});
    const [fgOriginData, setFgOriginData] = useState({});
    const [fgOriginDataLoading, setFgOriginDataLoading] = useState(true);
    const [fgMetrics, setFgMetrics] = useState({});
    const [fgMetricsLoading, setFgMetricsLoading] = useState(true);
    const [coresNodesCount, setCoresNodesCount] = useState({});
    const [coresNodesCountLoading, setCoresNodesCountLoading] = useState(true);
    const [zoomedFgData, setZoomedFgData] = useState({});
    const [isFgDisplayed, setIsFgDisplayed] = useState(false);
    const [isFgLoading, setIsFgLoading] = useState(false);
    const [viewTruncated, setViewTruncated] = useState(false);
    const [instanceType, setInstanceType] = useState({});
    const [instanceTypeLoading, setInstanceTypeLoading] = useState(true);
    const [mineSweeperMode, setMineSweeperMode] = useState(false);
    const [framesSelected, setFramesSelected] = useState([]);
    const [isFGEmpty, setIsFGEmpty] = useState(false);
    const [tableViewRows, setTableViewRows] = useState([]);

    useTruncationQueryParams({ viewTruncated, setViewTruncated });

    useEffect(() => {
        setFramesSelected([]);
    }, [timeSelection]);

    return (
        <FgContext.Provider
            value={{
                fgOriginData,
                setFgOriginData,
                fgOriginDataLoading,
                setFgOriginDataLoading,
                lastWeekOriginData,
                setLastWeekOriginData,
                zoomedFgData,
                setZoomedFgData,
                isFgDisplayed,
                setIsFgDisplayed,
                isFgLoading,
                setIsFgLoading,
                fgMetrics,
                setFgMetrics,
                fgMetricsLoading,
                setFgMetricsLoading,
                coresNodesCountLoading,
                setCoresNodesCountLoading,
                setCoresNodesCount,
                coresNodesCount,
                viewTruncated,
                setViewTruncated,
                instanceType,
                instanceTypeLoading,
                setInstanceTypeLoading,
                setInstanceType,
                mineSweeperMode,
                setMineSweeperMode,
                framesSelected,
                setFramesSelected,
                isFGEmpty,
                setIsFGEmpty,
                tableViewRows,
                setTableViewRows,
            }}>
            {children}
        </FgContext.Provider>
    );
};
