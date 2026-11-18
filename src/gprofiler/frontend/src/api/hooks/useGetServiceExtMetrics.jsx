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
import { useContext } from 'react';

import { FilterTagsContext } from '../../states/filters/FiltersTagsContext';
import { SelectorsContext } from '../../states/selectors';
import { DATA_URLS } from '../urls';
import useFetchWithRequest from '../useFetchWithRequest';
import { getStartEndDateTimeFromSelection } from '../utils';

const useExtBaseParams = () => {
    const { selectedService, timeSelection } = useContext(SelectorsContext);
    const { activeFilterTag } = useContext(FilterTagsContext);
    const filter = activeFilterTag?.filter ? JSON.stringify(activeFilterTag) : undefined;

    return {
        params: { ...getStartEndDateTimeFromSelection(timeSelection), serviceName: selectedService, filter },
        deps: [selectedService, timeSelection, filter],
        ready: !_.isUndefined(selectedService) && !_.isUndefined(timeSelection),
    };
};

export const useGetServiceExtMetricNames = () => {
    const { params, deps, ready } = useExtBaseParams();
    const { data, loading } = useFetchWithRequest(
        { url: DATA_URLS.GET_METRICS_EXT_NAMES + '?' + queryString.stringify(params) },
        { refreshDeps: deps, ready }
    );

    return { extNames: data, extNamesLoading: loading };
};

// Not fetched until a name is selected
export const useGetServiceExtMetricGraph = ({ resolution, name }) => {
    const { params, deps, ready } = useExtBaseParams();
    const query = {
        ...params,
        name,
        requested_interval: resolution ? resolution.slice(0, -1) : undefined, // in Clickhouse it is singular
    };
    const { data, loading } = useFetchWithRequest(
        { url: DATA_URLS.GET_METRICS_EXT_GRAPH + '?' + queryString.stringify(query) },
        { refreshDeps: [...deps, resolution, name], ready: ready && !!name }
    );

    return { extGraphData: data, extGraphLoading: loading };
};
