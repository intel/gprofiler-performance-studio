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

import {
    add,
    differenceInHours,
    differenceInMinutes,
    differenceInSeconds,
    format,
    formatISO9075,
    intervalToDuration,
    isBefore,
    isDate,
    isToday,
    isValid,
    isYesterday,
    parseISO,
    sub,
} from 'date-fns';

export const TIME_UNITS = {
    minutes: 'minutes',
    seconds: 'seconds',
    hours: 'hours',
    days: 'days',
};

export const TIME_FORMATS = {
    DATETIME_BASIC: `yyyy-MM-dd'T'HH:mm:00`,
    DATETIME_PRINTED: 'dd/MM/yyyy HH:mm',
    DATETIME_WITH_SECONDS: 'dd/MM/yyyy HH:mm:ss',
    DATE_BASIC: 'dd/MM/yyyy',
    TIME_24H: 'HH:mm',
};

// Datetime formatting
export const formatDate = (date, toFormat = TIME_FORMATS.DATETIME_BASIC) => {
    return format(date, toFormat);
};

export const localDatetimeToUtc = (datetime) => {
    datetime = datetime || new Date();
    return datetime.toISOString();
};

export const parseUtcToLocalDateTime = (startTime, endTime) => {
    if (!startTime || !endTime) {
        return undefined;
    }
    const localStartTime = formatDate(new Date(startTime), TIME_FORMATS.DATETIME_PRINTED);
    const localEndTime = formatDate(new Date(endTime), TIME_FORMATS.DATETIME_PRINTED);
    return `${localStartTime} - ${localEndTime}`;
};

export const parseUtcStringToDate = (stringDate) => {
    return parseISO(stringDate);
};

// Datetime manipulations
export const addTime = (date, unit = TIME_UNITS.minutes, unitsToAdd) => {
    const newDate = add(new Date(date), { [unit]: unitsToAdd });
    return newDate;
};

export const subDate = (date, unit = TIME_UNITS.minutes, unitsToSub) => {
    return sub(date, { [unit]: unitsToSub });
};

// Datetime validation
export const isValidDate = (date) => {
    return isDate(date) && isValid(date);
};

// UI visibility Datetimes
export const getLiteralDate = (date) => {
    if (isToday(date)) {
        return 'Today';
    }
    if (isDateYesterday(date)) {
        return 'Yesterday';
    }
    return formatDate(date, TIME_FORMATS.DATE_BASIC);
};

// Datetimes diffs calculations
export const getTimeDiff = (start, end) => {
    return intervalToDuration({ start, end });
};

export const getTimeDiffByUnit = (date1, date2, unit = TIME_UNITS.minutes) => {
    switch (unit) {
        case TIME_UNITS.minutes:
            return differenceInMinutes(date1, date2);
        case TIME_UNITS.seconds:
            return differenceInSeconds(date1, date2);
        case TIME_UNITS.hours:
            return differenceInHours(date1, date2);
        default:
            return;
    }
};

export const isDateLessThanTenMinutesAgo = (date1, date2) => {
    const diff = getTimeDiff(date1, date2);
    return (diff.minutes < 10 && diff.minutes > 0) || (diff.minutes === 0 && diff.seconds > 0);
};

export const isDateBefore = (date1, date2) => {
    return isBefore(date1, date2);
};

export const isDateYesterday = (date) => {
    return isYesterday(date);
};

// Datetimes creation
export const getCurrentTime = () => {
    return formatDate(new Date(), TIME_FORMATS.TIME_24H);
};
