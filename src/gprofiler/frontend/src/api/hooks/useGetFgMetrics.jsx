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
import queryString from 'query-string';
import { useContext, useState } from 'react';

import { isFilterTypeExist } from '@/components/filters/utils';
import { FILTER_TYPES } from '@/utils/filtersUtils';

import { FilterTagsContext } from '../../states/filters/FiltersTagsContext';
import { SelectorsContext } from '../../states/selectors';
import { PROFILES_VIEWS } from '../../utils/consts';
import { DATA_URLS } from '../urls';
import useFetchWithRequest from '../useFetchWithRequest';
import { getStartEndDateTimeFromSelection } from '../utils';

const areParamsDefined = (selectedService, timeSelection) => {
    return !_.isUndefined(selectedService) && !_.isUndefined(timeSelection);
};

const useGetFgMetrics = ({ customTimeSelection, customService, disableCoreNodesRequest = false }) => {
    const { selectedService, timeSelection, viewMode, ignoreZeros } = useContext(SelectorsContext);
    const { activeFilterTag } = useContext(FilterTagsContext);
    const [metricsData, setMetricsData] = useState(undefined);
    const [lastHtmlData, setLastHtmlData] = useState(undefined);
    const [coresNodesCountData, setCoresNodesCountData] = useState(undefined);
    const [instanceTypeData, setInstanceTypeData] = useState(undefined);
    const timeParams = getStartEndDateTimeFromSelection(customTimeSelection || timeSelection);

    const metricsParams = {
        serviceName: customService || selectedService,
        filter: activeFilterTag?.filter ? JSON.stringify(activeFilterTag) : undefined,
        ...timeParams,
    };

    const { loading: metricsLoading } = useFetchWithRequest(
        {
            url: DATA_URLS.GET_METRICS + '?' + queryString.stringify(metricsParams),
        },
        {
            refreshDeps: [
                customService,
                selectedService,
                customTimeSelection ? customTimeSelection : timeSelection,
                activeFilterTag,
            ],
            ready: areParamsDefined(customService || selectedService, customTimeSelection || timeSelection),
            onSuccess: (result) => {
                setMetricsData(result);
            },
            onError: () => {
                setMetricsData(undefined);
            },
        }
    );

    const isHostNameFilterActive = isFilterTypeExist(FILTER_TYPES.HostName.value, activeFilterTag);
    const { loading: lastHtmlLoading } = useFetchWithRequest(
        {
            url: DATA_URLS.GET_LAST_HTML + '?' + queryString.stringify(metricsParams),
        },
        {
            refreshDeps: [
                customService,
                selectedService,
                customTimeSelection ? customTimeSelection : timeSelection,
                activeFilterTag,
            ],
            ready:
                areParamsDefined(customService || selectedService, customTimeSelection || timeSelection) &&
                isHostNameFilterActive,
            onSuccess: (result) => {
                setLastHtmlData(result?.content);
            },
            onError: () => {
                setLastHtmlData(undefined);
            },
        }
    );

    const isServiceView = viewMode === PROFILES_VIEWS.service;
    const serviceAndTimeParams = {
        serviceName: customService || selectedService,
        ignoreZeros: ignoreZeros,
        ...timeParams,
        ...(!isServiceView
            ? {
                  filter: activeFilterTag?.filter ? JSON.stringify(activeFilterTag) : undefined,
              }
            : {}),
    };

    const { loading: coresNodesCountLoading } = useFetchWithRequest(
        {
            url: DATA_URLS.GET_NODES_AND_CORES + '?' + queryString.stringify(serviceAndTimeParams),
        },
        {
            refreshDeps: [
                customService,
                selectedService,
                customTimeSelection ? customTimeSelection : timeSelection,
                viewMode,
                activeFilterTag,
                ignoreZeros,
            ],
            ready:
                !disableCoreNodesRequest &&
                areParamsDefined(customService || selectedService, customTimeSelection || timeSelection),
            onSuccess: (result) => {
                setCoresNodesCountData(result);
            },
            onError: () => {
                setCoresNodesCountData(undefined);
            },
        }
    );

    const { loading: instanceTypeDataLoading } = useFetchWithRequest(
        {
            url: DATA_URLS.GET_INSTANCE_TYPE + '?' + queryString.stringify(serviceAndTimeParams),
        },
        {
            refreshDeps: [selectedService, customService, customTimeSelection ? customTimeSelection : timeSelection],
            ready: areParamsDefined(customService || selectedService, customTimeSelection || timeSelection),
            onSuccess: (result) => {
                setInstanceTypeData(result);
            },
            onError: () => {
                setInstanceTypeData(undefined);
            },
        }
    );
    return {
        metricsData,
        metricsLoading,
        lastHtmlData,
        lastHtmlLoading,
        coresNodesCountData: coresNodesCountData,
        coresNodesCountLoading,
        instanceTypeData,
        instanceTypeDataLoading,
    };
};

export default useGetFgMetrics;
