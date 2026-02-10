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

import _ from 'lodash';
import { useCallback, useContext, useEffect, useMemo, useState } from 'react';

import useGetFgMetrics from '@/api/hooks/useGetFgMetrics';
import HtmlView from '@/components/profiles/views/htmlView/HtmlView';

import {
    countZoomedSearchMatches,
    FgContext,
    FiltersContext,
    highlightColorsBySearchKeyword,
    returnTypeSearchIfMatches,
    SearchContext,
    SelectorsContext,
} from '../../states';
import { FgHoverContext } from '../../states/flamegraph/FgHoverContext';
import { PROFILES_VIEWS } from '../../utils/consts';
import {
    addMatched,
    createTableViewData,
    filterByPercentile,
    filterByProcessName,
    filterByThreshold,
    filterRuntime,
    getPercent,
    isFunctionLegit,
} from '../../utils/fgUtils';
import { STACK_TYPES } from '../../utils/filtersUtils';
import { clone } from '../../utils/generalUtils';
import { CUSTOM_PERCENTILE_VALUE } from './header/filters/weight/consts';
import ProfilesEmptyState from './ProfilesEmptyState';
import FlamegraphView from './views/flamegraph/FlamegraphView';
import { parseFlamegraphData } from './views/flamegraph/parsingUtils';
import ServiceView from './views/service/ServiceView';
import TableView from './views/table/TableView';

const ProfilesViews = () => {
    const { fgOriginData, lastWeekOriginData, zoomedFgData, setZoomedFgData, framesSelected, setIsFGEmpty, isFGEmpty } =
        useContext(FgContext);
    const { lastHtmlData } = useGetFgMetrics({});

    const { viewMode, selectedService, timeSelection } = useContext(SelectorsContext);
    const { setHoverData } = useContext(FgHoverContext);

    const {
        filters: { runtime: runtimeFilters, processes: processesFilters, weight: weightFilters },
        resetProcessFilters,
        resetRuntimeFilters,
        resetWeightFilters,
    } = useContext(FiltersContext);

    const {
        searchValue,
        setSearchValue,
        setMatchAmount,
        setSearchResult,
        setOwnAmount,
        setTotalMatchedAmount,
        setTotalOwnAmount,
    } = useContext(SearchContext);

    const [justSearched, setJustSearched] = useState(!!searchValue);

    useEffect(() => {
        if (!searchValue && justSearched) {
            setJustSearched(true);
        } else if (!justSearched && !searchValue) {
            setJustSearched(false);
        } else if (searchValue) {
            setJustSearched(true);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchValue]);

    useEffect(() => {
        resetWeightFilters();
    }, [setSearchValue, selectedService, timeSelection, resetProcessFilters, resetRuntimeFilters, resetWeightFilters]);

    const filteredData = useMemo(() => {
        let tempFilteredData = clone(fgOriginData);
        if (runtimeFilters.allRuntimes.length !== runtimeFilters.filters.length) {
            const isMixedStacks = viewMode !== PROFILES_VIEWS.table && runtimeFilters.isMixedRuntimeStacksModeEnabled;
            tempFilteredData = filterRuntime(
                tempFilteredData,
                runtimeFilters.allRuntimes.filter((runtime) => runtimeFilters.filters.includes(runtime.name)),
                isMixedStacks
            );
        }

        if (weightFilters.percentile === CUSTOM_PERCENTILE_VALUE) {
            if (weightFilters.threshold)
                tempFilteredData = filterByThreshold(
                    tempFilteredData,
                    (weightFilters.threshold / 100) * tempFilteredData.value
                );
        } else if (weightFilters.percentile) {
            tempFilteredData = filterByPercentile(tempFilteredData, weightFilters.percentile);
        }

        if (processesFilters.filters?.length > 0) {
            tempFilteredData = filterByProcessName(tempFilteredData, processesFilters.filters);
        }
        tempFilteredData = addMatched(tempFilteredData);
        return tempFilteredData;
    }, [
        fgOriginData,
        processesFilters,
        runtimeFilters.isMixedRuntimeStacksModeEnabled,
        runtimeFilters.filters,
        runtimeFilters.allRuntimes,
        weightFilters.threshold,
        weightFilters.percentile,
        viewMode,
    ]);

    useEffect(() => {
        setZoomedFgData(filteredData);
    }, [filteredData, setZoomedFgData]);

    const resetZoomedFgData = () => {
        setZoomedFgData(filteredData);
    };
    const searchedData = useMemo(() => {
        if (searchValue) {
            const isSearchByType = returnTypeSearchIfMatches(searchValue);
            return highlightColorsBySearchKeyword(filteredData, searchValue, isSearchByType);
        } else {
            return filteredData;
        }
    }, [filteredData, searchValue]);

    const flameGraphData = useMemo(() => {
        return [
            parseFlamegraphData(
                {
                    type: STACK_TYPES.root,
                    name: 'All',
                    matched: searchedData.matched,
                    value: searchedData.value,
                    children: searchedData.children,
                    percentiles: searchedData.percentiles,
                },
                0,
                0,
                false,
                true,
                framesSelected
            ),
        ];
    }, [searchedData, framesSelected]);

    useEffect(() => {
        if (!_.isEmpty(flameGraphData[0]) && flameGraphData[0]?.children?.length === 0) {
            setIsFGEmpty(true);
        } else {
            setIsFGEmpty(false);
        }
    }, [flameGraphData, setIsFGEmpty]);

    useEffect(() => {
        if (searchValue) {
            try {
                const isSearchByType = returnTypeSearchIfMatches(searchValue);
                let countedSearchMatches, totalMatch, totalOwn;
                if (viewMode === PROFILES_VIEWS.table) {
                    countedSearchMatches = countZoomedSearchMatches(filteredData, searchValue, isSearchByType);
                    totalMatch = filteredData?.value || filteredData?.duration;
                    totalOwn = filteredData?.value || filteredData?.duration;
                } else {
                    countedSearchMatches = countZoomedSearchMatches(zoomedFgData, searchValue, isSearchByType);
                    totalMatch = zoomedFgData?.value || zoomedFgData?.duration;
                    totalOwn = zoomedFgData?.value || zoomedFgData?.duration;
                }
                const { matchAmount, ownAmount } = countedSearchMatches;
                setMatchAmount(matchAmount);
                setOwnAmount(ownAmount);
                setTotalMatchedAmount(totalMatch);
                setTotalOwnAmount(totalOwn);
                setSearchResult('success');
            } catch (e) {
                setSearchResult(e.message);
            }
        } else {
            setSearchResult(null);
        }
    }, [
        searchedData,
        searchValue,
        setMatchAmount,
        zoomedFgData,
        setSearchResult,
        setOwnAmount,
        filteredData,
        viewMode,
        setTotalMatchedAmount,
        setTotalOwnAmount,
    ]);

    const tableViewData = useMemo(() => {
        if (viewMode === PROFILES_VIEWS.table) {
            const isSearchMode = !_.isEmpty(searchValue);
            const parsedProcessesList = processesFilters.processesList.map((item) => item.value);
            const tableViewData = createTableViewData(searchedData, lastWeekOriginData, isSearchMode);
            const FilteredTableViewData = tableViewData.filter((item) =>
                isFunctionLegit(item.function, parsedProcessesList)
            );
            return FilteredTableViewData;
        }
        return [];
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchedData, lastWeekOriginData, viewMode]);

    const getTooltipData = useCallback(
        (nodeData, renderEngine, mouse) => {
            if (nodeData?.data && mouse?.isInsideFg) {
                const { duration, name, children } = nodeData.data.source;
                const cpuTime = getPercent(duration, searchedData.value);
                const ownTime = getPercent(duration - _.sumBy(children, (child) => child.duration), searchedData.value);
                setHoverData({ name, ownTime, cpuTime, value: duration });
            } else {
                setHoverData('');
            }
        },
        [setHoverData, searchedData]
    );

    return viewMode === PROFILES_VIEWS.service ? (
        <ServiceView />
    ) : viewMode === PROFILES_VIEWS.table ? (
        <TableView timeSelection={timeSelection} rows={tableViewData} filteredData={filteredData} />
    ) : viewMode === PROFILES_VIEWS.html ? (
        <HtmlView lastHtml={lastHtmlData} />
    ) : !isFGEmpty ? (
        <FlamegraphView
            flameGraphData={flameGraphData}
            justSearched={justSearched}
            resetZoomedFgData={resetZoomedFgData}
            searchMode={searchValue}
            getTooltipData={getTooltipData}
            setHoverData={setHoverData}
            setZoomedFgData={setZoomedFgData}
        />
    ) : (
        <ProfilesEmptyState />
    );
};

export default ProfilesViews;
