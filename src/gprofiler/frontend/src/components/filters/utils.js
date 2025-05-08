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

import { FILTER_OPERATIONS } from '../../utils/filtersUtils';

export const isFilterTypeExist = (type, filter) => {
    if (!filter?.filter) return false;
    const [, rules] = Object.entries(filter.filter)[0];
    return rules?.some((rule) => {
        const [ruleType] = Object.entries(rule)[0];
        return type === ruleType;
    });
};

export const shouldShowFilterTypeOptions = (filter, { type, operator }) => {
    return operator === FILTER_OPERATIONS.$or.value || !isFilterTypeExist(type, filter);
};
