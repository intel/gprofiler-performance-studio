import { Box, Button, Collapse, FormControl, InputLabel, MenuItem, Select, TextField } from '@mui/material';
import React, { useState } from 'react';

import { COLORS } from '../../../theme/colors';
import Icon from '../../common/icon/Icon';
import { ICONS_NAMES } from '../../common/icon/iconsData';
import Flexbox from '../../common/layout/Flexbox';

const ProfilingHeader = ({ filters, updateFilter, isLoading = false, onApplyFilters, onClearFilters }) => {
    const [filtersExpanded, setFiltersExpanded] = useState(false);

    return (
        <Box sx={{ background: COLORS.ALMOST_WHITE, position: 'relative' }}>
            {/* Filter Toggle Button */}
            <Flexbox
                justifyContent='space-between'
                alignItems='center'
                sx={{ px: 4, py: 2, borderBottom: filtersExpanded ? '1px solid rgba(0, 0, 0, 0.12)' : 'none' }}>
                <Button
                    variant='outlined'
                    size='large'
                    onClick={() => setFiltersExpanded(!filtersExpanded)}
                    startIcon={<Icon name={ICONS_NAMES.Filter} />}
                    endIcon={
                        <Icon 
                            name={filtersExpanded ? ICONS_NAMES.ChevronDown : ICONS_NAMES.ChevronRight} 
                        />
                    }
                    sx={{
                        textTransform: 'none',
                        color: COLORS.PRIMARY_BLUE,
                        borderColor: COLORS.PRIMARY_BLUE,
                        fontSize: '16px',
                        fontWeight: 500,
                        px: 3,
                        py: 1.5,
                        minWidth: '180px',
                        '&:hover': {
                            borderColor: COLORS.PRIMARY_BLUE,
                            backgroundColor: 'rgba(30, 64, 175, 0.04)',
                        },
                    }}>
                    Filters
                </Button>
            </Flexbox>

            {/* Collapsible Filters Section */}
            <Collapse in={filtersExpanded} timeout='auto' unmountOnExit>
                <Flexbox
                    spacing={{ xs: 1, sm: 2, md: 4 }}
                    justifyContent='start'
                    sx={{ p: 4, zIndex: 3 }}>
                    <Box
                        sx={{
                            display: 'grid',
                            gridTemplateColumns: { 
                                xs: '1fr', 
                                sm: '1fr 1fr', 
                                md: '1fr 1fr 1fr', 
                                lg: '1fr 1fr 1fr 1fr 1fr 1fr' 
                            },
                            width: '100%',
                            gap: { xs: 2, sm: 2, md: 3 },
                        }}>
                {/* Service Name Filter */}
                <TextField
                    label='Service Name'
                    variant='outlined'
                    size='small'
                    value={filters.service}
                    onChange={(e) => updateFilter('service', e.target.value)}
                    placeholder='Filter by service...'
                    disabled={isLoading}
                    fullWidth
                    sx={{
                        backgroundColor: 'white !important',
                        borderRadius: '4px',
                        boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)',
                        '& .MuiOutlinedInput-root': {
                            backgroundColor: 'white !important',
                            '& fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                            },
                            '&:hover fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.87)',
                            },
                        },
                        '& .MuiInputBase-input': {
                            backgroundColor: 'white !important',
                        },
                    }}
                />

                {/* Hostname Filter */}
                <TextField
                    label='Hostname'
                    variant='outlined'
                    size='small'
                    value={filters.hostname}
                    onChange={(e) => updateFilter('hostname', e.target.value)}
                    placeholder='Filter by hostname...'
                    disabled={isLoading}
                    fullWidth
                    sx={{
                        backgroundColor: 'white !important',
                        borderRadius: '4px',
                        boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)',
                        '& .MuiOutlinedInput-root': {
                            backgroundColor: 'white !important',
                            '& fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                            },
                            '&:hover fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.87)',
                            },
                        },
                        '& .MuiInputBase-input': {
                            backgroundColor: 'white !important',
                        },
                    }}
                />

                {/* PIDs Filter */}
                <TextField
                    label='PIDs'
                    variant='outlined'
                    size='small'
                    value={filters.pids}
                    onChange={(e) => updateFilter('pids', e.target.value)}
                    placeholder='Filter by PIDs...'
                    disabled={isLoading}
                    fullWidth
                    sx={{
                        backgroundColor: 'white !important',
                        borderRadius: '4px',
                        boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)',
                        '& .MuiOutlinedInput-root': {
                            backgroundColor: 'white !important',
                            '& fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                            },
                            '&:hover fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.87)',
                            },
                        },
                        '& .MuiInputBase-input': {
                            backgroundColor: 'white !important',
                        },
                    }}
                />

                {/* IP Address Filter */}
                <TextField
                    label='IP Address'
                    variant='outlined'
                    size='small'
                    value={filters.ip}
                    onChange={(e) => updateFilter('ip', e.target.value)}
                    placeholder='Filter by IP...'
                    disabled={isLoading}
                    fullWidth
                    sx={{
                        backgroundColor: 'white !important',
                        borderRadius: '4px',
                        boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)',
                        '& .MuiOutlinedInput-root': {
                            backgroundColor: 'white !important',
                            '& fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                            },
                            '&:hover fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.87)',
                            },
                        },
                        '& .MuiInputBase-input': {
                            backgroundColor: 'white !important',
                        },
                    }}
                />

                {/* Command Type Filter */}
                <FormControl
                    size='small'
                    fullWidth
                    sx={{
                        backgroundColor: 'white !important',
                        borderRadius: '4px',
                        boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)',
                        '& .MuiOutlinedInput-root': {
                            backgroundColor: 'white !important',
                            '& fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                            },
                            '&:hover fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.87)',
                            },
                        },
                        '& .MuiSelect-select': {
                            backgroundColor: 'white !important',
                        },
                    }}>
                    <InputLabel>Command Type</InputLabel>
                    <Select
                        value={filters.commandType}
                        onChange={(e) => updateFilter('commandType', e.target.value)}
                        label='Command Type'
                        disabled={isLoading}>
                        <MenuItem value=''>All</MenuItem>
                        <MenuItem value='start'>start</MenuItem>
                        <MenuItem value='stop'>stop</MenuItem>
                    </Select>
                </FormControl>

                {/* Profiling Status Filter */}
                <FormControl
                    size='small'
                    fullWidth
                    sx={{
                        backgroundColor: 'white !important',
                        borderRadius: '4px',
                        boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.1)',
                        '& .MuiOutlinedInput-root': {
                            backgroundColor: 'white !important',
                            '& fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                            },
                            '&:hover fieldset': {
                                borderColor: 'rgba(0, 0, 0, 0.87)',
                            },
                        },
                        '& .MuiSelect-select': {
                            backgroundColor: 'white !important',
                        },
                    }}>
                    <InputLabel>Profiling Status</InputLabel>
                    <Select
                        value={filters.status}
                        onChange={(e) => updateFilter('status', e.target.value)}
                        label='Profiling Status'
                        disabled={isLoading}>
                        <MenuItem value=''>All</MenuItem>
                        <MenuItem value='pending'>pending</MenuItem>
                        <MenuItem value='running'>running</MenuItem>
                        <MenuItem value='completed'>completed</MenuItem>
                        <MenuItem value='failed'>failed</MenuItem>
                        <MenuItem value='stopped'>stopped</MenuItem>
                    </Select>
                </FormControl>
                    </Box>
                    
                    {/* Action Buttons */}
                    <Flexbox 
                        justifyContent='flex-end' 
                        gap={2}
                        sx={{ mt: 2 }}>
                        <Button
                            variant='outlined'
                            size='medium'
                            onClick={onClearFilters}
                            disabled={isLoading}
                            sx={{
                                textTransform: 'none',
                                borderColor: 'rgba(0, 0, 0, 0.23)',
                                color: 'rgba(0, 0, 0, 0.87)',
                                '&:hover': {
                                    borderColor: 'rgba(0, 0, 0, 0.87)',
                                    backgroundColor: 'rgba(0, 0, 0, 0.04)',
                                },
                            }}>
                            Clear
                        </Button>
                        <Button
                            variant='contained'
                            size='medium'
                            onClick={onApplyFilters}
                            disabled={isLoading}
                            sx={{
                                textTransform: 'none',
                                backgroundColor: COLORS.PRIMARY_BLUE,
                                '&:hover': {
                                    backgroundColor: '#1e3a8a',
                                },
                            }}>
                            Apply Filters
                        </Button>
                    </Flexbox>
                </Flexbox>
            </Collapse>
        </Box>
    );
};

export default ProfilingHeader;
