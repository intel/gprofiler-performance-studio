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

import {
    Box,
    Button,
    Chip,
    Collapse,
    FormControl,
    IconButton,
    InputLabel,
    MenuItem,
    Paper,
    Select,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Typography,
} from '@mui/material';
import { format } from 'date-fns';
import { stringify } from 'query-string';
import { useContext, useEffect, useState } from 'react';

import { DATA_URLS } from '@/api/urls';
import useFetchWithRequest from '@/api/useFetchWithRequest';
import { getStartEndDateTimeFromSelection } from '@/api/utils';
import Icon from '@/components/common/icon/Icon';
import { ICONS_NAMES } from '@/components/common/icon/iconsData';
import Flexbox from '@/components/common/layout/Flexbox';
import { SelectorsContext } from '@/states';
import { FilterTagsContext } from '@/states/filters/FiltersTagsContext';

const AdhocProfilingView = () => {
    const { selectedService, timeSelection, selectedHost } = useContext(SelectorsContext);
    const { activeFilterTag } = useContext(FilterTagsContext);
    const [selectedFile, setSelectedFile] = useState(null);
    const [selectedFileContent, setSelectedFileContent] = useState(null);
    const [isTableExpanded, setIsTableExpanded] = useState(true);

    const timeParams = getStartEndDateTimeFromSelection(timeSelection);

    const {
        data: filesData,
        loading: filesLoading,
        error: filesError,
        run: fetchFiles,
    } = useFetchWithRequest(
        {
            url: `${DATA_URLS.GET_ADHOC_FLAMEGRAPHS}?${stringify({
                serviceName: selectedService,
                ...timeParams,
                filter: activeFilterTag?.filter ? JSON.stringify(activeFilterTag) : undefined,
            })}`,
        },
        { manual: true }
    );

    const {
        data: fileContent,
        loading: contentLoading,
        error: contentError,
        run: fetchFileContent,
    } = useFetchWithRequest(
        {
            url: `${DATA_URLS.GET_ADHOC_FLAMEGRAPH_CONTENT}?${stringify({
                serviceName: selectedService,
                filename: selectedFile?.filename,
            })}`,
        },
        { manual: true }
    );

    useEffect(() => {
        if (selectedService && timeSelection) {
            fetchFiles();
            setSelectedFile(null);
            setSelectedFileContent(null);
        }
    }, [selectedService, timeSelection, activeFilterTag, selectedHost, fetchFiles]);

    useEffect(() => {
        if (selectedFile) {
            fetchFileContent();
        }
    }, [selectedFile, fetchFileContent]);

    useEffect(() => {
        if (fileContent) {
            // Handle both direct content string and object with content property
            const htmlContent = typeof fileContent === 'string' ? fileContent : fileContent.content;
            setSelectedFileContent(htmlContent);
        } else {
            setSelectedFileContent(null);
        }
    }, [fileContent]);

    const handleFileSelect = (event) => {
        const filename = event.target.value;
        const file = filesData?.find((f) => f.filename === filename);
        setSelectedFile(file);
    };

    const handleRowClick = (file) => {
        if (file.removed) return;
        setSelectedFile(file);
    };

    if (filesLoading) {
        return <Typography>Loading adhoc flamegraphs...</Typography>;
    }

    if (filesError) {
        return <Typography color='error'>Error loading adhoc flamegraphs: {filesError.message}</Typography>;
    }

    return (
        <Flexbox column sx={{ height: '100%', width: '100%', p: 2 }}>
            <Box
                sx={{
                    mb: 2,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 2,
                    backgroundColor: filesData && filesData.length > 0 ? 'grey.100' : 'transparent',
                    p: filesData && filesData.length > 0 ? 2 : 0,
                    borderRadius: 1,
                    cursor: filesData && filesData.length > 0 ? 'pointer' : 'default',
                    '&:hover': filesData && filesData.length > 0 ? { backgroundColor: 'grey.200' } : {},
                }}
                onClick={() => filesData && filesData.length > 0 && setIsTableExpanded(!isTableExpanded)}>
                <Typography variant='h6'>Adhoc Profiling</Typography>
                {filesData && filesData.length > 0 && (
                    <>
                        <FormControl sx={{ minWidth: 200 }}>
                            <InputLabel id='select-file-label'>Select Flamegraph File</InputLabel>
                            <Select
                                labelId='select-file-label'
                                value={selectedFile?.filename || ''}
                                label='Select Flamegraph File'
                                onChange={handleFileSelect}
                                onClick={(e) => e.stopPropagation()}>
                                {filesData.map((file) => (
                                    <MenuItem key={file.filename} value={file.filename} disabled={file.removed}>
                                        {format(new Date(file.timestamp), 'yyyy-MM-dd HH:mm:ss')} -{' '}
                                        {file.hostname || 'N/A'}
                                        {file.removed && ' (removed)'}
                                    </MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                        <Box sx={{ ml: 'auto', display: 'flex', alignItems: 'center' }}>
                            <Icon name={isTableExpanded ? ICONS_NAMES.ChevronDown : ICONS_NAMES.ChevronRight} />
                        </Box>
                    </>
                )}
            </Box>

            {filesData && filesData.length > 0 ? (
                <Box
                    sx={{
                        flexGrow: 1,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 2,
                        height: 'calc(100vh - 300px)',
                    }}>
                    <Collapse in={isTableExpanded}>
                        <TableContainer component={Paper} sx={{ maxHeight: 300, overflowY: 'auto', flexShrink: 0 }}>
                            <Table stickyHeader size='small'>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Timestamp</TableCell>
                                        <TableCell>Hostname</TableCell>
                                        <TableCell>PMU Events</TableCell>
                                        <TableCell>Size</TableCell>
                                        <TableCell>Action</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {filesData.map((file) => {
                                        const removedCellSx = file.removed
                                            ? { textDecoration: 'line-through', color: 'text.disabled' }
                                            : {};
                                        return (
                                            <TableRow
                                                key={file.filename}
                                                onClick={() => handleRowClick(file)}
                                                selected={selectedFile?.filename === file.filename}
                                                sx={{
                                                    cursor: file.removed ? 'default' : 'pointer',
                                                    '&:hover': file.removed ? {} : { backgroundColor: 'action.hover' },
                                                }}>
                                                <TableCell sx={removedCellSx}>
                                                    {format(new Date(file.timestamp), 'yyyy-MM-dd HH:mm:ss')}
                                                </TableCell>
                                                <TableCell sx={removedCellSx}>{file.hostname || 'N/A'}</TableCell>
                                                <TableCell sx={removedCellSx}>
                                                    {file.perf_events && file.perf_events.length > 0
                                                        ? file.perf_events.join(', ')
                                                        : 'N/A'}
                                                </TableCell>
                                                <TableCell sx={removedCellSx}>
                                                    {file.size ? `${(file.size / 1024).toFixed(2)} KB` : 'N/A'}
                                                </TableCell>
                                                <TableCell>
                                                    {file.removed ? (
                                                        <Chip
                                                            label='Removed'
                                                            size='small'
                                                            color='error'
                                                            variant='outlined'
                                                        />
                                                    ) : (
                                                        <Button
                                                            size='small'
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                handleRowClick(file);
                                                            }}>
                                                            View
                                                        </Button>
                                                    )}
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Collapse>

                    {contentLoading && <Typography>Loading flamegraph content...</Typography>}
                    {contentError && (
                        <Typography color='error'>Error loading flamegraph content: {contentError.message}</Typography>
                    )}
                    {selectedFileContent ? (
                        <Box
                            sx={{
                                flexGrow: 1,
                                width: '100%',
                                minHeight: 0,
                                display: 'flex',
                                border: '1px solid',
                                borderColor: 'divider',
                                borderRadius: 1,
                                overflow: 'hidden',
                            }}>
                            <iframe
                                style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
                                title='Adhoc Flamegraph'
                                srcDoc={selectedFileContent}
                                sandbox='allow-scripts allow-same-origin'
                            />
                        </Box>
                    ) : selectedFile && !contentLoading && !contentError ? (
                        <Typography>Click view to load flamegraph content</Typography>
                    ) : null}
                </Box>
            ) : (
                <Typography>No adhoc flamegraphs found for the selected service and time range.</Typography>
            )}
        </Flexbox>
    );
};

export default AdhocProfilingView;
