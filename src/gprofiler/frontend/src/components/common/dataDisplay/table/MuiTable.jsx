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
import { DataGrid } from '@mui/x-data-grid';

import {
    AutoHeightStyles,
    DarkPaginationStyles,
    MuiTableCustomLoadingOverlay,
    MuiTableCustomPagination,
    MuiTableDarkStyles,
    MuiTableStyles,
} from './muiTable.styles';

const MuiTable = ({
    columns,
    data,
    isLoading = false,
    initialState = {},
    pageSize = 15,
    rowHeight = 35,
    variant = 'light',
    multipleLinesCells = false,
    padding = 0,
    search = undefined,
    emptyStateComponent = undefined,
    footer = undefined,
    hideFooter = false,
    onRowClick = undefined,
    getRowId = undefined,
    autoPageSize = false,
    size = 'normal',
    sx = undefined,
    checkboxSelection = false,
    onSelectionModelChange = undefined,
    selectionModel = [],
}) => {
    const isDarkMode = variant !== 'light';
    const isSmallTableMode = size === 'small';
    return (
        <Box
            sx={{
                width: '100%',
                '& .compare-column': {
                    backgroundColor: 'fieldBlue.main',
                },
                p: padding,
                ...(isDarkMode && DarkPaginationStyles),
                ...(multipleLinesCells && data && AutoHeightStyles(data.length)),
            }}>
            <DataGrid
                sx={{
                    ...(isDarkMode ? MuiTableDarkStyles(isSmallTableMode) : MuiTableStyles(isSmallTableMode)),
                    ...sx,
                }}
                components={{
                    Pagination: MuiTableCustomPagination,
                    LoadingOverlay: MuiTableCustomLoadingOverlay,
                    Toolbar: search ? search.component : null,
                    NoRowsOverlay: emptyStateComponent,
                    Footer: footer ? () => footer : undefined,
                }}
                componentsProps={{
                    toolbar: search ? search.props : {},
                }}
                onRowClick={onRowClick}
                loading={isLoading}
                autoHeight
                pagination
                hideFooter={hideFooter}
                pageSize={pageSize}
                rowHeight={rowHeight}
                headerHeight={40}
                rows={data}
                columns={columns}
                disableColumnFilter
                disableColumnMenu
                disableColumnSelector
                initialState={initialState}
                disableVirtualization={multipleLinesCells}
                getRowId={getRowId}
                autoPageSize={autoPageSize}
                checkboxSelection={checkboxSelection}
                onSelectionModelChange={onSelectionModelChange}
                selectionModel={selectionModel}
            />
        </Box>
    );
};

export default MuiTable;
