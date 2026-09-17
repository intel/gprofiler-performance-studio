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

import ContainerEnvNameDescription from '../components/filters/descriptions/ContainerEnvNameDescription';
import ContainerNameDescription from '../components/filters/descriptions/ContainerNameDescription';
import HostnameDescription from '../components/filters/descriptions/HostnameDescription';
import { COLORS } from '../theme/colors';

export const SPECIAL_STACKS = [
    { name: 'Appid', color: COLORS.STACKS.Appid },
    {
        name: 'Java (inl)',
        color: COLORS.STACKS['Java (inl)'],
    },
    {
        name: 'Java (C1)',
        color: COLORS.STACKS['Java (C1)'],
    },
    {
        name: 'Java (interpreted)',
        color: COLORS.STACKS['Java (interpreted)'],
    },
];

export const STACKS_MAP = {
    Java: {
        name: 'Java',
        color: COLORS.STACKS.Java,
        functionNameRegex: new RegExp(`[^/]+\\.[^\\(]+`, 'i'),
    },
    Python: {
        name: 'Python',
        color: COLORS.STACKS.Python,
        functionNameRegex: new RegExp(`([^\\.]+) \\(`, 'i'),
    },
    PHP: { name: 'PHP', color: COLORS.STACKS.PHP },
    Ruby: { name: 'Ruby', color: COLORS.STACKS.Ruby },
    Node: { name: 'Node', color: COLORS.STACKS.Node },
    '.NET': { name: '.NET', color: COLORS.STACKS['.NET'] },
    'C++': { name: 'C++', color: COLORS.STACKS['C++'] },
    Kernel: { name: 'Kernel', color: COLORS.STACKS.Kernel },
    Go: {
        name: 'Go',
        color: COLORS.STACKS.Go,
        functionNameRegex: new RegExp(`.*\\.([^\\.]+)`, 'i'),
    },
    Other: { name: 'Other', color: COLORS.STACKS.Other },
};

export const STACK_TYPES = {
    Java: STACKS_MAP.Java.name,
    Python: STACKS_MAP.Python.name,
    PHP: STACKS_MAP.PHP.name,
    Ruby: STACKS_MAP.Ruby.name,
    Node: STACKS_MAP.Node.name,
    CPlus: STACKS_MAP['C++'].name,
    DotNet: STACKS_MAP['.NET'].name,
    Kernel: STACKS_MAP.Kernel.name,
    Other: STACKS_MAP.Other.name,
    Go: STACKS_MAP.Go.name,
    root: 'root',
    Appid: 'Appid',
    mine: 'mine',
    JavaInl: 'Java (inl)',
    JavaC1: 'Java (C1)',
    JavaC0: 'Java (interpreted)',
};

export const specialTypesKeys = ['javainl', 'javac1', 'javac0'];

export const specialTypesKeysToRealTypes = {
    javainl: STACK_TYPES.JavaInl,
    javac1: STACK_TYPES.JavaC1,
    javac0: STACK_TYPES.JavaC0,
};

export const stacksToFgColors = () => {
    return [...Object.values(STACKS_MAP), ...SPECIAL_STACKS, ...SPECIAL_STACKS].reduce(
        (previousValues, currentStack) => ({ ...previousValues, [currentStack.name]: currentStack.color }),
        {
            root: COLORS.STACKS.root,
            mine: COLORS.STACKS.mine,
            limit: COLORS.ERROR_RED,
        }
    );
};

export const getColorByRuntime = (runtime) => {
    return STACKS_MAP[runtime || STACK_TYPES.Other]?.color;
};

export const getColorBySpecialType = (specialType) => {
    return COLORS.STACKS[specialType || 'Appid'];
};

export const getRuntimesList = () => {
    return Object.values(STACKS_MAP);
};

export const getRuntimesFunctionNameRegex = (runtime) => {
    return STACKS_MAP[runtime || STACK_TYPES.other]?.functionNameRegex;
};

export const ECS_DESCRIPTION_TITLE = 'ECS';
export const K8S_DESCRIPTION_TITLE = 'K8S';

export const FILTER_TYPES = {
    ContainerName: {
        value: 'ContainerName',
        display: 'Container name',
        counterLabel: 'Container',
        description: <ContainerNameDescription />,
    },
    HostName: {
        value: 'HostName',
        display: 'Host name',
        counterLabel: 'Host',
        description: <HostnameDescription />,
    },
    ContainerEnvName: {
        value: 'ContainerEnvName',
        display: 'Deployment name',
        counterLabel: 'Deployment',
        description: <ContainerEnvNameDescription />,
    },
};

export const FILTER_OPERATIONS = {
    $and: { value: '$and', display: 'And' },
    $or: { value: '$or', display: 'Or' },
};

export const FILTER_EQUALNESS = {
    $eq: { value: '$eq', display: 'Is' },
    $neq: { value: '$neq', display: 'Is not' },
    $like: { value: '$like', display: 'Contains' },
};
