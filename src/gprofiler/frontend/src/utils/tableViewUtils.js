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

export const getFunctioNameEdges = (functionName, coreFunctionName) => {
    const coreFunctionIndex = functionName.indexOf(coreFunctionName);
    const coreFunctionLength = coreFunctionName.length;

    const nameStart = functionName.substring(0, coreFunctionIndex);
    const nameEnd = functionName.substring(coreFunctionIndex + coreFunctionLength, functionName.length);
    return { start: nameStart, end: nameEnd };
};

export const TABLE_CSV_COLUMNS = [
    { header: 'Runtime', getValue: (row) => row.specialType || row.runtime },
    { header: 'Function name', getValue: (row) => row.function },
    { header: 'Samples', getValue: (row) => row.samples },
    { header: 'Total CPU (%)', getValue: (row) => row.totalTime },
    { header: 'Own Time (%)', getValue: (row) => row.ownTime },
    { header: 'Trend (%)', getValue: (row) => row.trend?.trend },
    { header: 'Occurrences', getValue: (row) => row.occurrencesNum },
];

const escapeCsvCell = (value) => {
    if (value === null || value === undefined) return '';
    let text = String(value);
    // Keep spreadsheet apps from evaluating function names such as "=foo" as formulas
    if (typeof value === 'string' && /^[=+\-@\t\r]/.test(text)) {
        text = `'${text}`;
    }
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

// Builds the CSV text of the Table View rows, sorted like the table's default order (Total CPU, descending)
export const buildTableViewCsv = (rows = []) => {
    const sortedRows = [...rows].sort((a, b) => b.totalTime - a.totalTime);
    const lines = [TABLE_CSV_COLUMNS.map(({ header }) => escapeCsvCell(header))];
    sortedRows.forEach((row) => {
        lines.push(TABLE_CSV_COLUMNS.map(({ getValue }) => escapeCsvCell(getValue(row))));
    });
    return lines.map((line) => line.join(',')).join('\r\n');
};
