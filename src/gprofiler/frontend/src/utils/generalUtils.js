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

/*
 * Trampoline to avoid recursion in JavaScript, see:
 *     https://www.integralist.co.uk/posts/functional-recursive-javascript-programming/
 */
function trampoline() {
    let func = arguments[0];
    let args = [];
    for (let i = 1; i < arguments.length; i++) {
        args[i - 1] = arguments[i];
    }

    let currentBatch = func.apply(this, args);
    let nextBatch = [];

    while (currentBatch && currentBatch.length > 0) {
        currentBatch.forEach(function (eachFunc) {
            let ret = eachFunc();
            if (ret && ret.length > 0) {
                nextBatch = nextBatch.concat(ret);
            }
        });

        currentBatch = nextBatch;
        nextBatch = [];
    }
}

/*
 *  Deep clone an object using the trampoline technique.
 */
function clone(target) {
    if (typeof target !== 'object') {
        return target;
    }
    if (target === null || Object.keys(target).length === 0) {
        return target;
    }

    function _clone(b, a) {
        var nextBatch = [];
        for (var key in b) {
            if (key === '__proto__' || key === 'constructor') {
                continue; // Skip unsafe properties
            }
            if (typeof b[key] === 'object' && b[key] !== null) {
                if (b[key] instanceof Array) {
                    a[key] = [];
                } else {
                    a[key] = {};
                }
                nextBatch.push(_clone.bind(null, b[key], a[key]));
            } else {
                a[key] = b[key];
            }
        }
        return nextBatch;
    }

    var ret = target instanceof Array ? [] : {};
    trampoline.bind(null, _clone)(target, ret);
    return ret;
}

/*
 *  merge two arrays of objects by key
 */
const mergeArrays = (arr1, arr2, key) => {
    const mergeHelper = new Map(arr1.map((x) => [x[key], x]));
    for (const x of arr2) {
        if (mergeHelper.has(x[key])) {
            const item = mergeHelper.get(x[key]);
            mergeHelper.set(x[key], { ...item, ...x });
        } else {
            mergeHelper.set(x[key], x);
        }
    }
    return [...mergeHelper.values()];
};
const isPathSecure = () => window?.location.protocol === 'https:';

export { clone, isPathSecure, mergeArrays };
