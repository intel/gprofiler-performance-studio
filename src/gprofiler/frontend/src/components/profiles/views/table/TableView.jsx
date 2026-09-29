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

import { Box } from '@mui/material';
import PropTypes from 'prop-types';
import { memo, useEffect, useMemo, useState } from 'react';
import { useResizeObserver } from 'use-resize-observer';

import MuiTable from '@/components/common/dataDisplay/table/MuiTable';
import Flexbox from '@/components/common/layout/Flexbox';
import { useWindowSize } from '@/hooks/useWindowSize';

import { projectFgDataIntoTableView } from '../../../../utils/fgUtils';
import LegendBoxContainer from '../legendBox/LegendBoxContainer';
import { SplitView, SplitViewDivider } from './SplitView';
import { PROFILES_TABLE_COLUMNS } from './TableViewColumns';
import { getGeneratedTimeSelectionText } from './utils';

const TableView = memo(({ rows = [], filteredData = {}, timeSelection }) => {
    const tableMappingData = useMemo(() => {
        return projectFgDataIntoTableView(filteredData.children, filteredData.value);
    }, [filteredData]);

    // for creating the canvas size
    const { ref, width = 1, height = 1 } = useResizeObserver();
    // for deciding how many rows the table will be
    const { height: windowHeight } = useWindowSize();
    const tableRowsCount = windowHeight ? Math.floor((windowHeight - 320) / 35) : 10;

    const [rowSelected, setRowSelected] = useState(undefined);
    const [tableColumns, setTableColumns] = useState(
        PROFILES_TABLE_COLUMNS(getGeneratedTimeSelectionText(timeSelection), rowSelected)
    );

    useEffect(() => {
        setTableColumns(PROFILES_TABLE_COLUMNS(getGeneratedTimeSelectionText(timeSelection), rowSelected));
    }, [timeSelection, rowSelected]);

    return (
        <Box>
            <div
                ref={ref}
                style={{
                    overflow: 'hidden',
                    position: 'relative',
                    width: '100%',
                    height: '100%',
                    minHeight: 'calc(80vh - 250px)',
                }}>
                <Flexbox sx={{ m: 4, mb: 3, borderRadius: 2, boxShadow: 3 }}>
                    <Box sx={{ width: '100%', overFlow: 'scroll' }}>
                        <MuiTable
                            pageSize={tableRowsCount}
                            data={rows}
                            columns={tableColumns}
                            rowHeight={35}
                            onRowClick={(params) => setRowSelected(params.row)}
                            initialState={{
                                sorting: {
                                    sortModel: [{ field: 'totalTime', sort: 'desc' }],
                                },
                                columns: {
                                    columnVisibilityModel: { suffix: false, specialType: false },
                                },
                            }}
                            sx={{ border: rowSelected ? 'none' : '' }}
                        />
                    </Box>

                    {rowSelected && <SplitViewDivider setRowSelected={setRowSelected} />}
                    {rowSelected && (
                        <SplitView
                            fgData={rowSelected}
                            tableMappingData={tableMappingData}
                            width={width / 2}
                            height={height - 60}
                        />
                    )}
                </Flexbox>
            </div>
            <Flexbox justifyContent='center'>
                <LegendBoxContainer disabled={rowSelected} />
            </Flexbox>
        </Box>
    );
});

TableView.displayName = 'TableView';

TableView.propTypes = {
    rows: PropTypes.array,
    timeSelection: PropTypes.object,
};

export default TableView;
