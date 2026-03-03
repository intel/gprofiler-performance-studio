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
import { createContext, useCallback, useContext, useEffect, useReducer, useState } from 'react';

import useGetServiceFilters from '../../api/filters/useGetServiceFilters';
import useMainFiltersQueryParams from '../../hooks/useMainFiltersQueryParams';
import { FILTER_EQUALNESS, FILTER_TYPES } from '../../utils/filtersUtils';
import { SelectorsContext } from '../selectors';

export const FilterTagsContext = createContext({
    filter: {},
    dispatchFilterTags: () => {},
    activeFilterTag: {},
    setActiveFilterTag: () => {},
    resetActiveTagFilters: () => {},
    savedFilters: [],
    savedFiltersLoading: false,
    getSavedFilters: () => {},
    activeFiltersCount: {},
});

const initialFilters = {
    id: '',
    filter: {
        $and: [{ [FILTER_TYPES.ContainerName.value]: { [FILTER_EQUALNESS.$eq.value]: '' } }],
    },
};

export const FILTER_TAGS_ACTIONS = {
    CLEAR: 'CLEAR',
    SET: 'SET',
    ADD: 'ADD',
    DELETE: 'DELETE',
    OPERATION_CHANGE: 'OPERATION_CHANGE',
    TYPE_CHANGE: 'TYPE_CHANGE',
    EQ_CHANGE: 'EQ_CHANGE',
    VALUE_CHANGE: 'VALUE_CHANGE',
};

const getActiveFiltersTagCounters = (activeFilterTag) => {
    const { filter } = activeFilterTag;
    const count = filter.$and?.length || 0 + filter?.$or.length || 0;
    return count || 0;
};

export const FilterTagsContextProvider = ({ children }) => {
    const [filter, dispatchFilterTags] = useReducer(reducer, initialFilters);
    const [activeFilterTag, setActiveFilterTag] = useState(undefined);
    const [activeFiltersCount, setActiveFiltersCount] = useState(undefined);
    const { savedFilters, savedFiltersLoading, getSavedFilters } = useGetServiceFilters();

    const { selectedService } = useContext(SelectorsContext);

    const { resetActiveTagFiltersQuery } = useMainFiltersQueryParams({ activeFilterTag, setActiveFilterTag });

    const resetActiveTagFilters = useCallback(() => {
        if (!_.isEmpty(activeFilterTag)) {
            setActiveFilterTag(undefined);
            dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.CLEAR });
        }
        resetActiveTagFiltersQuery();
    }, [resetActiveTagFiltersQuery, setActiveFilterTag, activeFilterTag]);

    useEffect(() => {
        if (activeFilterTag) {
            dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.SET, payload: activeFilterTag });
            setActiveFiltersCount(getActiveFiltersTagCounters(activeFilterTag));
        } else {
            setActiveFiltersCount(undefined);
        }
    }, [dispatchFilterTags, activeFilterTag]);

    useEffect(() => {
        if (selectedService) {
            setActiveFilterTag(undefined);
            dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.CLEAR });
        }
    }, [selectedService]);

    return (
        <FilterTagsContext.Provider
            value={{
                filter,
                dispatchFilterTags,
                resetActiveTagFilters,
                activeFilterTag,
                setActiveFilterTag,
                savedFilters,
                savedFiltersLoading,
                getSavedFilters,
                activeFiltersCount,
            }}>
            {children}
        </FilterTagsContext.Provider>
    );
};

const reducer = (state, action) => {
    const { type, payload, index } = action;
    switch (type) {
        case FILTER_TAGS_ACTIONS.SET:
            return payload;
        case FILTER_TAGS_ACTIONS.ADD: {
            const [operation0, rules0] = Object.entries(state.filter)[0];
            return {
                id: state.id,
                filter: {
                    [operation0]: [
                        ...rules0,
                        { [FILTER_TYPES.ContainerName.value]: { [FILTER_EQUALNESS.$eq.value]: '' } },
                    ],
                },
            };
        }
        case FILTER_TAGS_ACTIONS.DELETE:
            const [operation1, rules1] = Object.entries(state.filter)[0];
            const filteredRules = rules1.filter((rule, ruleIndex) => ruleIndex !== index);
            return {
                id: state.id,
                filter: {
                    [operation1]: filteredRules,
                },
            };
        case FILTER_TAGS_ACTIONS.OPERATION_CHANGE:
            const [, rules] = Object.entries(state.filter)[0];
            return { id: state.id, filter: { [payload]: rules } };
        case FILTER_TAGS_ACTIONS.TYPE_CHANGE:
            const [operation, rules2] = Object.entries(state.filter)[0];
            return {
                id: state.id,
                filter: {
                    [operation]: rules2.map((rule, ruleIndex) => {
                        if (ruleIndex === index) {
                            const [, subItem] = Object.entries(rule)[0];

                            const [equal, value] = Object.entries(subItem)[0];
                            return { [payload]: { [equal]: '' } };
                        }
                        return rule;
                    }),
                },
            };
        case FILTER_TAGS_ACTIONS.EQ_CHANGE:
            const [operation2, rules3] = Object.entries(state.filter)[0];
            return {
                id: state.id,
                filter: {
                    [operation2]: rules3.map((rule, ruleIndex) => {
                        if (ruleIndex === index) {
                            const [type, subItem] = Object.entries(rule)[0];
                            const [, value] = Object.entries(subItem)[0];
                            return { [type]: { [payload]: value } };
                        }
                        return rule;
                    }),
                },
            };
        case FILTER_TAGS_ACTIONS.VALUE_CHANGE:
            const [operation3, rules4] = Object.entries(state.filter)[0];
            return {
                id: state.id,
                filter: {
                    [operation3]: rules4.map((rule, ruleIndex) => {
                        if (ruleIndex === index) {
                            const [type, subItem] = Object.entries(rule)[0];
                            const [equal] = Object.entries(subItem)[0];
                            return { [type]: { [equal]: payload } };
                        }
                        return rule;
                    }),
                },
            };

        case FILTER_TAGS_ACTIONS.CLEAR:
            return initialFilters;
        default:
            break;
    }
};
