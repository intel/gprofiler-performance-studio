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

import { createContext, useEffect, useState } from 'react';

import useGraphTabQueryParams from '@/hooks/useGraphTabsQueryParams';

import useGraphViewQueryParams from '../../hooks/useGraphViewQueryParams';
import useServicePickQueryParams from '../../hooks/useServicePickQueryParams';
import useTimePickQueryParams from '../../hooks/useTimePickQueryParams';
import { PROFILES_VIEWS } from '../../utils/consts';
import { DEFAULT_INITIAL_TIME_RANGE_FILTER } from '../../utils/fgUtils';

export const SelectorsContext = createContext();

export const SelectorsProvider = ({ children }) => {
    const [services, setServices] = useState([]);
    const [viewMode, setViewMode] = useState(PROFILES_VIEWS.flamegraph);
    const [selectedGraphTab, setSelectedGraphTab] = useState('1');
    const [areServicesLoading, setAreServicesLoading] = useState(true);
    const { selectedService, setSelectedService } = useServicePickQueryParams({ services });
    const [ignoreZeros, setIgnoreZeros] = useState(true);
    const [selectedServiceEnvType, setSelectedServiceEnvType] = useState('');

    const [timeSelection, setTimeSelectionState] = useState({ relativeTime: DEFAULT_INITIAL_TIME_RANGE_FILTER });
    const [absoluteTimeSelection, setAbsoluteTimeSelection] = useState({ startTime: '', endTime: '' });

    const [timeFetched, setTimeFetched] = useState(undefined);
    const setTimeSelection = useTimePickQueryParams({
        setTimeSelection: setTimeSelectionState,
        timeSelection,
    });
    const resetSelectedTimeRange = () => {
        setTimeSelection({ relativeTime: DEFAULT_INITIAL_TIME_RANGE_FILTER });
    };

    //save envType of selected service
    useEffect(() => {
        if (selectedService) {
            const foundService = services.find((service) => service.name === selectedService);
            if (foundService) {
                setSelectedServiceEnvType(foundService.envType);
            } else {
                setSelectedServiceEnvType('');
            }
        } else {
            setSelectedServiceEnvType('');
        }
    }, [selectedService, services]);

    useGraphViewQueryParams({ viewMode, setViewMode });
    useGraphTabQueryParams({ selectedGraphTab, setSelectedGraphTab });

    return (
        <SelectorsContext.Provider
            value={{
                services,
                setServices,
                areServicesLoading,
                setAreServicesLoading,
                selectedService,
                selectedServiceEnvType,
                setSelectedService,
                timeSelection,
                viewMode,
                setViewMode,
                setTimeSelection,
                timeFetched,
                setTimeFetched,
                absoluteTimeSelection,
                setAbsoluteTimeSelection,
                resetSelectedTimeRange,
                ignoreZeros,
                setIgnoreZeros,
                selectedGraphTab,
                setSelectedGraphTab,
            }}>
            {children}
        </SelectorsContext.Provider>
    );
};
