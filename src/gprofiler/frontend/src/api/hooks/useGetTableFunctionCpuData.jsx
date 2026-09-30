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

import { FilterTagsContext } from '../../states/filters/FiltersTagsContext';
import { SelectorsContext } from '../../states/selectors';
import { DATA_URLS } from '../urls';
import useFetchWithRequest from '../useFetchWithRequest';
import { getStartEndDateTimeFromSelection } from '../utils';

const areParamsDefined = (selectedService, timeSelection, functionName) => {
    return !_.isUndefined(selectedService) && !_.isUndefined(timeSelection) && !!functionName;
};

const useGetTableFunctionCpuData = ({ functionName, customService, customTimeSelection }) => {
    const { selectedService, timeSelection } = useContext(SelectorsContext);
    const { activeFilterTag } = useContext(FilterTagsContext);

    const [parsedData, setParsedData] = useState([]);
    const metricsParams = {
        serviceName: customService || selectedService,
        filter: activeFilterTag?.filter ? JSON.stringify(activeFilterTag) : undefined,
        functionName,
    };

    const timeParams = getStartEndDateTimeFromSelection(customTimeSelection || timeSelection);
    const { data: functionCpuData, loading: functionCpuLoading } = useFetchWithRequest(
        {
            url:
                DATA_URLS.GET_FUCNTION_CPU_GRAPH +
                '?' +
                queryString.stringify(_.assign({ ...timeParams }, metricsParams)),
        },
        {
            refreshDeps: [
                customService ? customService : selectedService,
                customTimeSelection ? customTimeSelection : timeSelection,
                functionName,
            ],
            ready: areParamsDefined(
                customService ? customService : selectedService,
                customTimeSelection ? customTimeSelection : timeSelection,
                functionName
            ),
            onBefore: () => setParsedData([]),
            onSuccess: (result) => {
                setParsedData(
                    result.map((cpuData) => {
                        return {
                            cpu_percentage: cpuData.cpu_percentage * 100,
                            time: cpuData.time,
                        };
                    })
                );
            },
        }
    );
    return {
        functionCpuData: parsedData,
        functionCpuLoading,
    };
};

export default useGetTableFunctionCpuData;
