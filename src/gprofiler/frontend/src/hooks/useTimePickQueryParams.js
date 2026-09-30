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

import { useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { StringParam, useQueryParams } from 'use-query-params';

import { isValidDate } from '@/utils/datetimesUtils';

import { PAGES } from '../utils/consts';
import { DEFAULT_INITIAL_TIME_RANGE_FILTER } from '../utils/fgUtils';
import { isDateQueryParamsExists, MAP_FILTER_QUERY_TO_TIME, MAP_TIME_TO_FILTER_QUERY } from '../utils/timeRangeUtils';

const TIME_QUERY_PARAM = 'time';
const START_TIME_QUERY_PARAM = 'startTime';
const END_TIME_QUERY_PARAM = 'endTime';

const useTimePickQueryParams = ({ setTimeSelection, timeSelection, customQueryParams = undefined }) => {
    let location = useLocation();
    const TIME_QUERY = customQueryParams ? customQueryParams.time : TIME_QUERY_PARAM;
    const START_TIME_QUERY = customQueryParams ? customQueryParams.start : START_TIME_QUERY_PARAM;
    const END_TIME_QUERY = customQueryParams ? customQueryParams.end : END_TIME_QUERY_PARAM;

    const [queryParams, setQueryParams] = useQueryParams({
        [TIME_QUERY]: StringParam,
        [START_TIME_QUERY]: StringParam,
        [END_TIME_QUERY]: StringParam,
    });

    const time = queryParams[TIME_QUERY];
    const startTime = queryParams[START_TIME_QUERY];
    const endTime = queryParams[END_TIME_QUERY];

    const updateTimeQueryParams = useCallback(
        (newTimeSelection, updateType) => {
            if (newTimeSelection.relativeTime) {
                setQueryParams(
                    {
                        [TIME_QUERY]: MAP_TIME_TO_FILTER_QUERY[newTimeSelection.relativeTime],
                        [START_TIME_QUERY]: undefined,
                        [END_TIME_QUERY]: undefined,
                    },
                    updateType
                );
            } else if (newTimeSelection.customTime) {
                setQueryParams(
                    {
                        [TIME_QUERY]: undefined,
                        [START_TIME_QUERY]: newTimeSelection.customTime?.startTime?.toISOString(),
                        [END_TIME_QUERY]: newTimeSelection.customTime?.endTime?.toISOString(),
                    },
                    updateType
                );
            }
        },
        [END_TIME_QUERY, START_TIME_QUERY, TIME_QUERY, setQueryParams]
    );

    const setTimeSelectionFromUser = useCallback(
        (newTimeSelection) => {
            setTimeSelection(newTimeSelection);
            if (location.pathname === PAGES.profiles.to || location.pathname === PAGES.comparison.to) {
                updateTimeQueryParams(newTimeSelection, 'pushIn');
            }
        },
        [location.pathname, setTimeSelection, updateTimeQueryParams]
    );

    useEffect(() => {
        if (time || (startTime && endTime)) {
            if (!time && isValidDate(new Date(startTime)) && isValidDate(new Date(endTime))) {
                setTimeSelection({ customTime: { startTime: new Date(startTime), endTime: new Date(endTime) } });
            } else if (isDateQueryParamsExists(time)) {
                setTimeSelection({ relativeTime: MAP_FILTER_QUERY_TO_TIME[time] });
            } else {
                setTimeSelection({ relativeTime: DEFAULT_INITIAL_TIME_RANGE_FILTER });
            }
        }
    }, [endTime, setTimeSelection, startTime, time]);

    useEffect(() => {
        if (
            (location.pathname === PAGES.profiles.to || location.pathname === PAGES.comparison.to) &&
            !time &&
            !(startTime && endTime)
        ) {
            updateTimeQueryParams(timeSelection, 'replaceIn');
        }
    }, [endTime, location.pathname, startTime, time, timeSelection, updateTimeQueryParams]);

    return setTimeSelectionFromUser;
};

export default useTimePickQueryParams;
