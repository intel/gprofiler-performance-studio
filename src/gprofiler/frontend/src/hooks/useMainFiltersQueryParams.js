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

import { PAGES } from '../utils/consts';
import { FILTER_EQUALNESS, FILTER_OPERATIONS, FILTER_TYPES } from '../utils/filtersUtils';

const mapFilterToQueryParam = {
    [FILTER_TYPES.ContainerName.value]: 'cn',
    [FILTER_TYPES.HostName.value]: 'hn',
    [FILTER_TYPES.ContainerEnvName.value]: 'cen',
};

const mapQueryParamToFilter = {
    cn: [FILTER_TYPES.ContainerName.value],
    hn: [FILTER_TYPES.HostName.value],
    cen: [FILTER_TYPES.ContainerEnvName.value],
};

const mapOperatorToQueryParam = {
    [FILTER_OPERATIONS.$and.value]: 'a',
    [FILTER_OPERATIONS.$or.value]: 'o',
};

const mapEqualToQueryParam = {
    [FILTER_EQUALNESS.$eq.value]: 'is',
    [FILTER_EQUALNESS.$neq.value]: 'not',
    [FILTER_EQUALNESS.$like.value]: 'has',
};
const mapQueryParamToEqual = {
    is: [FILTER_EQUALNESS.$eq.value],
    not: [FILTER_EQUALNESS.$neq.value],
    has: [FILTER_EQUALNESS.$like.value],
};

const delimiter = ',';

const parseFilterToQueryParam = (filter) => {
    const [operation, rules] = Object.entries(filter.filter)[0];

    return rules
        .map((rule) => {
            const [type, subItem] = Object.entries(rule)[0];
            const [equal, value] = Object.entries(subItem)[0];
            return mapFilterToQueryParam[type] + delimiter + mapEqualToQueryParam[equal] + delimiter + value;
        })
        .join(delimiter + mapOperatorToQueryParam[operation] + delimiter);
};

const AND_IDENIFIER = `${delimiter}a${delimiter}`;

const parseQueryParamsToFilter = (filter) => {
    const splittedFilter = filter.split(/,o,|,a,/);
    const operator = filter.includes(AND_IDENIFIER) ? FILTER_OPERATIONS.$and.value : FILTER_OPERATIONS.$or.value;
    const rules = [];
    splittedFilter.forEach((rule) => {
        const parsedRule = splitAndAppend(rule, delimiter, 2);
        rules.push({
            type: mapQueryParamToFilter[parsedRule[0]],
            equal: mapQueryParamToEqual[parsedRule[1]],
            value: parsedRule[2],
        });
    });
    return {
        [operator]: rules.map((rule) => {
            return { [rule.type]: { [rule.equal]: rule.value } };
        }),
    };
};

const splitAndAppend = (str, delim, count) => {
    const arr = str.split(delim);
    return [...arr.splice(0, count), arr.join(delim)];
};

const useMainFiltersQueryParams = ({ activeFilterTag, setActiveFilterTag }) => {
    let location = useLocation();
    const [queryParams, setQueryParams] = useQueryParams({
        filter: StringParam,
    });
    const { filter } = queryParams;

    const handleFilterChange = useCallback(() => {
        //set query params by filters

        setQueryParams({
            filter: activeFilterTag ? parseFilterToQueryParam(activeFilterTag) : undefined,
        });
    }, [setQueryParams, activeFilterTag]);

    useEffect(() => {
        if (location.pathname === PAGES.profiles.to) {
            handleFilterChange();
        }
    }, [activeFilterTag, handleFilterChange, location.pathname]);

    useEffect(() => {
        //set filters by query params if they exist

        if (filter) {
            const parsedFilter = parseQueryParamsToFilter(filter);
            // Apply the URL filter synchronously on mount. A previous 3s
            // setTimeout here caused the view to load once unfiltered and then
            // reload with the filter a beat later.
            setActiveFilterTag({ id: '', filter: parsedFilter });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const resetActiveTagFiltersQuery = () => {
        setQueryParams({ filter: undefined });
    };
    return { resetActiveTagFiltersQuery };
};

export default useMainFiltersQueryParams;
