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

import { useContext, useEffect } from 'react';

import useGetFgData from '../../api/hooks/useGetFgData';
import useGetFgMetrics from '../../api/hooks/useGetFgMetrics';
import UsePageTitle from '../../hooks/usePageTitle';
import { FgContext, SelectorsContext } from '../../states';
import { PROFILES_VIEWS } from '../../utils/consts';
import { getUpdatedFgData } from '../../utils/fgUtils';
import FGLoader from './FGLoader';
import ProfilesEmptyState from './ProfilesEmptyState';
import ProfilesViewsWrapper from './ProfilesViewsWrapper';

const ProfilesWrapper = () => {
    const {
        setFgOriginData,
        setFgOriginDataLoading,
        setZoomedFgData,
        setLastWeekOriginData,
        setIsFgDisplayed,
        setIsFgLoading,
        setFgMetrics,
        setCoresNodesCount,
        setCoresNodesCountLoading,
        setFgMetricsLoading,
        setInstanceTypeLoading,
        setInstanceType,
    } = useContext(FgContext);

    const { data, error, lastWeekDataError, lastWeekData, isLastWeekDataLoading, loading } = useGetFgData({});
    const {
        metricsData,
        metricsLoading,
        coresNodesCountData,
        coresNodesCountLoading,
        instanceTypeData,
        instanceTypeDataLoading,
    } = useGetFgMetrics({});
    UsePageTitle();
    const { viewMode } = useContext(SelectorsContext);
    const isFgDisplayed = !error && !lastWeekDataError && !loading && !isLastWeekDataLoading && data && !!data?.value;
    // Adhoc view doesn't depend on flamegraph data, so always show it when selected
    const shouldShowView = isFgDisplayed || viewMode === PROFILES_VIEWS.adhoc;

    useEffect(() => {
        if (!loading && data) {
            const updatedData = getUpdatedFgData(data);
            setFgOriginData(updatedData);
            setZoomedFgData(updatedData);
            setFgOriginDataLoading(false);
        }
        if (loading) {
            setFgOriginDataLoading(true);
        }
    }, [data, loading, setFgOriginData, setZoomedFgData, setFgOriginDataLoading]);

    useEffect(() => {
        if (!isLastWeekDataLoading && lastWeekData && lastWeekData?.success !== false) {
            setLastWeekOriginData(getUpdatedFgData(lastWeekData));
        }
    }, [isLastWeekDataLoading, lastWeekData, setLastWeekOriginData]);

    useEffect(() => {
        setIsFgDisplayed(isFgDisplayed);
        setIsFgLoading(loading || isLastWeekDataLoading);
    }, [setIsFgDisplayed, isFgDisplayed, setIsFgLoading, loading, isLastWeekDataLoading]);

    useEffect(() => {
        if (coresNodesCountLoading) {
            setCoresNodesCount({});
            setCoresNodesCountLoading(true);
        } else {
            setCoresNodesCount(coresNodesCountData);
            setCoresNodesCountLoading(false);
        }
    }, [coresNodesCountData, coresNodesCountLoading, setCoresNodesCount, setCoresNodesCountLoading]);

    useEffect(() => {
        if (metricsLoading) {
            setFgMetricsLoading(true);
            setFgMetrics({});
        } else {
            setFgMetrics(metricsData);
            setFgMetricsLoading(false);
        }
    }, [metricsData, metricsLoading, setFgMetrics, setFgMetricsLoading]);

    useEffect(() => {
        if (instanceTypeDataLoading) {
            setInstanceType({});
            setInstanceTypeLoading(true);
        } else {
            setInstanceType(instanceTypeData);
            setInstanceTypeLoading(false);
        }
    }, [instanceTypeData, setInstanceTypeLoading, setInstanceType, instanceTypeDataLoading]);

    return (
        <>
            {loading || isLastWeekDataLoading ? (
                <FGLoader />
            ) : (
                <>{!shouldShowView ? <ProfilesEmptyState errorMessage={error} /> : <ProfilesViewsWrapper />}</>
            )}
        </>
    );
};

export default ProfilesWrapper;
