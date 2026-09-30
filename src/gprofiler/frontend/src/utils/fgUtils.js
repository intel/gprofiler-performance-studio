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

import { getStartEndDateTimeFromSelection } from '../api/utils';
import { PAGES } from './consts';
import { subDate, TIME_UNITS } from './datetimesUtils';
import { getRuntimesFunctionNameRegex, STACK_TYPES, STACKS_MAP } from './filtersUtils';

const unknownNode = {
    name: STACKS_MAP.Other.name,
    color: STACKS_MAP.Other.color,
};
const DEPTH_LIMIT = 800;
const isTruncatedNode = (nodeName) => nodeName.endsWith('_[t]');

const getDepth = (tree, depth) => {
    if (tree.children.length > 0) {
        return Math.max(tree.children.map((child) => getDepth(child, depth + 1))) || 0;
    }
    return depth;
};

// For creating a colored and without suffixes fg
const updateNode = (node, depth = 0, specialTypeOverwrite = undefined) => {
    const matchingStack = STACKS_MAP[node.language || 'Other'] || STACKS_MAP['Other'];
    if (depth > DEPTH_LIMIT) {
        return {
            ...node,
            name: `depth limit reached (${DEPTH_LIMIT})`,
            type: 'limit',
            children: [],
        };
    }
    return {
        ...node,
        type: matchingStack.name,
        ...(specialTypeOverwrite ? { specialType: specialTypeOverwrite } : {}),
        children: node.children.map((childNode) => updateNode(childNode, depth + 1)),
    };
};

const getUpdatedFgData = (fgData) => {
    return {
        type: 'root',
        name: fgData.name,
        value: fgData.value,
        children: fgData.children.map((childNode) => updateNode(childNode, 0, STACK_TYPES.Appid)),
        percentiles: fgData.percentiles,
    };
};

const isNodeMatch = (activeRuntimeFilters, stackName) => {
    return !!_.find(activeRuntimeFilters, { name: stackName });
};

const filterStackChildren = (newParent, oldChild, activeRuntimeFilters, isMixedStacksOn) => {
    _.each(oldChild.children, (child) => {
        filterStacks(newParent, { ...child }, activeRuntimeFilters, isMixedStacksOn);
    });
};

//Recursive function for creating the new Runtime filtered fg. If isMixedStacksOn is true, we add all the matched node's children
const filterStacks = (newParent, oldChild, activeRuntimeFilters, isMixedStacksOn) => {
    const nodeMatch = isNodeMatch(activeRuntimeFilters, oldChild.type || unknownNode.name);
    if (nodeMatch) {
        const node = { ...oldChild };
        newParent.children.push(node);
        if (!isMixedStacksOn) {
            node.children = [];
            filterStackChildren(node, oldChild, activeRuntimeFilters, isMixedStacksOn);
        }
    } else {
        filterStackChildren(newParent, oldChild, activeRuntimeFilters, isMixedStacksOn);
    }
};

const filterRuntime = (nonColoredData, updatedActiveRuntimeFilters, isMixedStacksOn) => {
    let newRoot = {
        name: nonColoredData.name,
        type: STACK_TYPES.root,
        percentiles: nonColoredData.percentiles,
        value: 0,
        children: [],
    };
    _.each(nonColoredData.children, (firstLvlChild) => {
        const node = {
            ...firstLvlChild, //as long as process name is unknown
            children: [],
        };

        _.each(firstLvlChild.children, (child) => {
            filterStacks(node, child, updatedActiveRuntimeFilters, isMixedStacksOn);
        });
        if (_.size(node.children) > 0) {
            newRoot.children.push(node);
            newRoot.value += node.value;
            newRoot.name = 'root';
        }
    });
    return newRoot;
};

const filterData = (data, predicate) =>
    _.reduce(
        data,
        (list, entry) => {
            if (predicate(entry)) {
                // if the object matches the filter, clone it after filtering
                // it's children
                list.push(
                    _.assign({}, entry, {
                        children: !entry.children ? null : filterData(entry.children, predicate),
                    })
                );
            }
            return list;
        },
        []
    );

const filterByThreshold = (nonColoredData, threshold) => {
    const newRoot = { ...nonColoredData };
    newRoot.children = filterData(newRoot.children, (item) => item.value >= threshold);
    // Re-calculate samples - required for flamegraph to be properly sized
    newRoot.value = _.sumBy(newRoot.children, 'value');
    return newRoot;
};

const filterByPercentile = (nonColoredData, percentile) => {
    if (percentile === 100) return nonColoredData;
    const thresholdNumber = nonColoredData.percentiles[100 - percentile];
    return filterByThreshold(nonColoredData, thresholdNumber);
};

const filterByProcessName = (fgOriginData, listOfCheckedProcesses) => {
    if (_.isEmpty(listOfCheckedProcesses)) {
        return fgOriginData;
    }
    const newFgData = {
        name: 'root',
        children: [],
        value: 0,
        type: STACK_TYPES.root,
    };
    newFgData.children = _.filter(fgOriginData.children, (item) => _.includes(listOfCheckedProcesses, item.name));
    const RootValue = _.sumBy(newFgData.children, 'value');
    newFgData.name = 'root';
    newFgData.value = RootValue;
    return newFgData;
};

const countFramesRecursively = (tree) => {
    const nodesWithChildren = _.filter(tree.children, (child) => child?.children?.length > 0);
    const nodesWithoutChildren = _.filter(tree.children, (child) => child?.children?.length <= 0);
    const truncatedNodes = _.filter(nodesWithoutChildren, (child) => isTruncatedNode(child.name));
    let sum = tree?.children?.length ? tree.children.length - truncatedNodes.length : 0;
    nodesWithChildren.forEach((element) => {
        sum += countFramesRecursively(element);
    });
    return sum;
};

const countFramesByPercentile = (data, percentile) => {
    const filteredData = filterByPercentile(data, percentile);
    return countFramesRecursively(filteredData);
};

const getPercent = (numerator, denominator) => {
    return numerator && denominator ? _.round((numerator / denominator) * 100, 2) : 0;
};

//For flameDb
export const TIME_RANGE_FILTERS = [
    { id: '15min', text: 'Last 15 min' },
    { id: '30min', text: 'Last 30 min' },
    { id: 'hourly', text: 'Last hour' },
    { id: '6h', text: 'Last 6 hours' },
    { id: 'daily', text: 'Last day' },
    { id: 'weekly', text: 'Last week' },
    { id: 'custom', text: 'Custom time' },
    { id: 'lastSnapshot', text: 'Last snapshot' },
];

export const TIME_RANGE_RELATIVE_DATE_METHOD = {
    '15min': () => subDate(new Date(), TIME_UNITS.minutes, 15),
    '30min': () => subDate(new Date(), TIME_UNITS.minutes, 30),
    hourly: () => subDate(new Date(), TIME_UNITS.hours, 1),
    '6h': () => subDate(new Date(), TIME_UNITS.hours, 6),
    daily: () => subDate(new Date(), TIME_UNITS.days, 1),
    weekly: () => subDate(new Date(), TIME_UNITS.days, 7),
};

export const CUSTOM_TIME_KEY = 'custom';
export const LAST_SNAPSHOT_TIME_KEY = 'lastSnapshot';
export const DEFAULT_INITIAL_TIME_RANGE_FILTER = TIME_RANGE_FILTERS[2].id;

const getTimeRangeText = (time_ranges, timeRangeId) => {
    return _.find(time_ranges, { id: timeRangeId }).text;
};

const isFunctionLegit = (name, processesList) => {
    if (name === '[unknown]') return false;
    if (processesList.includes(name)) return false;
    return true;
};

const createTableViewData = (rootElement, lastWeekDataRootElement, isSearchMode) => {
    const dataObject = projectFgDataIntoTableView(rootElement.children, rootElement.value, isSearchMode);
    const currentData = Object.values(dataObject);
    const lastWeekData = projectFgDataIntoTableView(
        lastWeekDataRootElement.children,
        lastWeekDataRootElement.value,
        false
    );
    return _.map(currentData, (functionElement, index) => {
        const samplesPercentage = (functionElement.samples / rootElement.value) * 100;
        const lastWeekSamplesPercentage =
            lastWeekData[functionElement.function] && !!lastWeekDataRootElement.value
                ? (lastWeekData[functionElement.function].samples / lastWeekDataRootElement.value) * 100
                : 0;
        return {
            id: index,
            runtime: functionElement.runtime,
            specialType: functionElement.specialType,
            function: functionElement.function,
            shortFunction: getShortFunctionName(functionElement.function, functionElement.runtime),
            samples: functionElement.samples,
            suffix: functionElement.suffix,
            trend: {
                samplesPercentage: _.round(samplesPercentage, 2),
                lastWeekSamplesPercentage: _.round(lastWeekSamplesPercentage, 2),
                trend: lastWeekSamplesPercentage
                    ? _.round((samplesPercentage / lastWeekSamplesPercentage - 1) * 100, 2)
                    : null,
            },
            occurrences: functionElement.occurrences,
            occurrencesNum: functionElement.occurrences.length,
            parents: functionElement.parents,
            totalTime: _.round((functionElement.samples / rootElement.value) * 100, 2),
            ownTime: _.round((functionElement.ownSamples / rootElement.value) * 100, 2).toFixed(2),
        };
    });
};

const getShortFunctionName = (functionName, runtime) => {
    const functionNameRegex = getRuntimesFunctionNameRegex(runtime);
    if (!functionNameRegex) {
        return functionName;
    }

    const match = functionName.match(functionNameRegex);
    return match ? `${match.length > 1 ? match[1] : match[0]}` : functionName;
};

export const projectFgDataIntoTableView = (
    data,
    totalSamples,
    isSearchMode,
    currentStackSamples = [],
    parent,
    accumulator = {}
) => {
    return _.reduce(
        data,
        (accumulator, entry) => {
            if (entry.name.indexOf('-Truncated-') !== -1) return accumulator;
            if (isSearchMode && !entry.matched) {
                return projectFgDataIntoTableView(
                    entry.children,
                    totalSamples,
                    isSearchMode,
                    currentStackSamples,
                    entry,
                    accumulator
                );
            }
            if (!Object.prototype.hasOwnProperty.call(accumulator, entry.name)) {
                accumulator[entry.name] = {
                    runtime: entry.type,
                    specialType: entry.specialType,
                    function: entry.name,
                    suffix: entry.suffix,
                    samples: entry.value,
                    ownSamples: entry.value - _.sumBy(entry.children, 'value'),
                    occurrences: [entry],
                    parents: parent ? [parent] : [],
                };
            } else {
                if (!currentStackSamples.includes(entry.name)) {
                    accumulator[entry.name].samples += entry.value;
                }
                accumulator[entry.name].ownSamples += entry.value - _.sumBy(entry.children, 'value');
                accumulator[entry.name].occurrences.push(entry);
                accumulator[entry.name].parents.push(parent);
            }
            if (entry.children) {
                return projectFgDataIntoTableView(
                    entry.children,
                    totalSamples,
                    isSearchMode,
                    [...currentStackSamples, entry.name],
                    entry,
                    accumulator
                );
            } else {
                return accumulator;
            }
        },
        accumulator
    );
};

const addMatched = (flamegraphObject) => {
    return {
        matched: true,
        ...flamegraphObject,
        children: (flamegraphObject.children || []).map((child) => addMatched(child)),
    };
};

export const buildPermaLink = (timeSelection, search, snapshotId = '') => {
    let shareableLinkParams = queryString.parse(search);
    const isRelativeTimeInParams = _.includes(_.keys(shareableLinkParams), 'time');

    if (isRelativeTimeInParams) {
        const absoluteTimeSelection = getStartEndDateTimeFromSelection(timeSelection, true);
        shareableLinkParams = {
            ..._.omit(shareableLinkParams, ['time']),
            ...absoluteTimeSelection,
        };
    }

    // replace old snapshotId from url
    if (snapshotId) {
        shareableLinkParams = {
            ..._.omit(shareableLinkParams, ['snapshot']),
            snapshot: snapshotId,
        };
    }
    let shareableLink = `${window.location.protocol}//${window.location.host}${
        PAGES.profiles.to
    }?${queryString.stringify(shareableLinkParams)}`;
    return shareableLink;
};

export const buildAbsolutePermaLink = (timeSelection, search) => {
    let shareableLinkParams = queryString.parse(search);
    shareableLinkParams = {
        ..._.omit(shareableLinkParams, ['time', 'startTime', 'endTime']),
        ...timeSelection,
    };

    let shareableLink = `${window.location.protocol}//${window.location.host}${
        PAGES.profiles.to
    }?${queryString.stringify(shareableLinkParams)}`;
    return shareableLink;
};

export const buildComparisonPermaLink = (timeSelection, compareTimeSelection, search) => {
    let shareableLinkParams = queryString.parse(search);

    shareableLinkParams = {
        ..._.omit(shareableLinkParams, ['time', 'cTime', 'startTime', 'endTime', 'cStartTime', 'cEndTime']),
        ...timeSelection,
        ...compareTimeSelection,
    };

    let shareableLink = `${window.location.protocol}//${window.location.host}${
        PAGES.comparison.to
    }?${queryString.stringify(shareableLinkParams)}`;
    return shareableLink;
};

export {
    addMatched,
    countFramesByPercentile,
    createTableViewData,
    filterByPercentile,
    filterByProcessName,
    filterByThreshold,
    filterRuntime,
    getPercent,
    getTimeRangeText,
    getUpdatedFgData,
    isFunctionLegit,
};
