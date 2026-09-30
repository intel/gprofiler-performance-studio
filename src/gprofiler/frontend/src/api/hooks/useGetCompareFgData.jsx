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

import { DATA_URLS } from '../urls';
import useFetchWithRequest from '../useFetchWithRequest';
import { getStartEndDateTimeFromSelection } from '../utils';

const areParamsDefined = (selectedService, timeSelection) => {
    return !_.isUndefined(selectedService) && !_.isUndefined(timeSelection);
};

const useGetCompareFgData = ({ timeSelection, service, setAbsoluteCompareTime }) => {
    const fgParams = {
        serviceName: service,
        enrichment: ['lang'],
    };
    const timeParams = getStartEndDateTimeFromSelection(timeSelection);
    const { data, loading, error } = useFetchWithRequest(
        {
            url: `${DATA_URLS.GET_FLAMEGRAPH}?${queryString.stringify(_.assign({ ...timeParams }, fgParams))}`,
        },
        {
            refreshDeps: [service, timeSelection],
            ready: areParamsDefined(service, timeSelection),
            onSuccess: () => {
                setAbsoluteCompareTime({
                    cStartTime: timeParams.startTime,
                    cEndTime: timeParams.endTime,
                });
            },
        }
    );

    return { compareData: data, isCompareLoading: loading, error };
};

export default useGetCompareFgData;
