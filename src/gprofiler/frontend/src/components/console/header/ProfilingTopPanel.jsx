import { Box, Button, Divider, Typography, FormControlLabel, Checkbox, Tooltip, TextField, Radio, RadioGroup, Accordion, AccordionSummary, AccordionDetails } from '@mui/material';
import React from 'react';

import { COLORS } from '../../../theme/colors';
import Flexbox from '../../common/layout/Flexbox';

const PanelDivider = () => <Divider orientation='vertical' sx={{ borderColor: 'grey.dark', opacity: 0.1 }} flexItem />;

const ProfilingTopPanel = ({
    selectionModel,
    handleBulkAction,
    fetchProfilingStatus,
    filters,
    loading,
    rowsCount,
    clearAllFilters,
    enablePerfSpect,
    onPerfSpectChange,
    profilingFrequency,
    onProfilingFrequencyChange,
    maxProcesses,
    onMaxProcessesChange,
    profilerConfigs,
    onProfilerConfigsChange,
}) => {
    const hasActiveFilters = Object.values(filters).some((value) => value);

    // Helper function to handle profiler config changes
    const handleProfilerConfigChange = (profilerKey, value) => {
        onProfilerConfigsChange(prev => ({
            ...prev,
            [profilerKey]: value
        }));
    };

    // Profiler configuration definitions
    const profilerDefinitions = [
        {
            key: 'perf',
            name: 'Perf Profiler',
            description: 'C, C++, Go, Kernel',
            options: [
                { value: 'enabled_restricted', label: 'Enabled Restricted', tooltip: 'Profiles only top N containers/process', default: true },
                { value: 'enabled_aggressive', label: 'Enabled Aggressive', tooltip: 'Profiles all processes' },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'async_profiler',
            name: 'Async Profiler',
            description: 'Java',
            options: [
                { value: 'enabled', label: 'Enabled', default: true },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'pyperf',
            name: 'Pyperf',
            description: "Python's highly optimized eBPF. Exception - arm64 hosts",
            options: [
                { value: 'enabled', label: 'Enabled', default: true },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'pyspy',
            name: 'Pyspy',
            description: 'Python',
            options: [
                { value: 'enabled_fallback', label: 'Enabled as Fallback for Pyperf', default: true },
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'rbspy',
            name: 'Rbspy',
            description: 'Ruby',
            options: [
                { value: 'enabled', label: 'Enabled', default: true },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'phpspy',
            name: 'PHPspy',
            description: 'PHP',
            options: [
                { value: 'enabled', label: 'Enabled', default: true },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'dotnet_trace',
            name: '.NET Trace',
            description: '.NET',
            options: [
                { value: 'enabled', label: 'Enabled', default: true },
                { value: 'disabled', label: 'Disabled' }
            ]
        },
        {
            key: 'nodejs_perf',
            name: 'Perf',
            description: 'NodeJS',
            options: [
                { value: 'enabled', label: 'Enabled', default: true },
                { value: 'disabled', label: 'Disabled' }
            ]
        }
    ];

    return (
        <Flexbox column spacing={2}>
            <Box
                sx={{
                    background: `linear-gradient(180deg,${COLORS.ALMOST_WHITE} 50%, ${COLORS.WHITE} 50%)`,
                    px: 4,
                    zIndex: 1,
                }}>
                <Flexbox
                    spacing={4}
                    justifyContent='space-between'
                    alignItems='center'
                    sx={{
                        height: '45px',
                        width: '100%',
                        backgroundColor: 'white.main',
                        boxShadow: '0px 8px 12px rgba(9, 30, 66, 0.15), 0px 0px 1px rgba(9, 30, 66, 0.31)',
                        borderRadius: '26px',
                        px: 5,
                    }}>
                    {/* Left side - Action Buttons */}
                    <Flexbox alignItems='center' spacing={2} divider={<PanelDivider />}>
                        <Button
                            variant='contained'
                            color='success'
                            size='small'
                            onClick={() => handleBulkAction('start')}
                            disabled={selectionModel.length === 0}>
                            Start ({selectionModel.length})
                        </Button>
                        <Button
                            variant='contained'
                            color='error'
                            size='small'
                            onClick={() => handleBulkAction('stop')}
                            disabled={selectionModel.length === 0}>
                            Stop ({selectionModel.length})
                        </Button>
                        <Button
                            variant='outlined'
                            color='primary'
                            size='small'
                            onClick={() => fetchProfilingStatus(filters)}
                            disabled={loading}>
                            Refresh
                        </Button>
                        
                        {/* PerfSpect Hardware Metrics Checkbox */}
                        <Tooltip title="Enable Intel PerfSpect hardware metrics collection (auto-installs on agents)">
                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={enablePerfSpect}
                                        onChange={(e) => onPerfSpectChange(e.target.checked)}
                                        size="small"
                                        color="primary"
                                    />
                                }
                                label={
                                    <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
                                        PerfSpect HW Metrics
                                    </Typography>
                                }
                                sx={{ ml: 1 }}
                            />
                        </Tooltip>
                        
                        {/* Profiling Frequency Field */}
                        <Tooltip title="Number of samples per second for profiling duration (Hz)">
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 5 }}>
                                <Typography variant="body2" sx={{ fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                                    Profiling Frequency:
                                </Typography>
                                <TextField
                                    value={profilingFrequency}
                                    onChange={(e) => {
                                        const value = parseInt(e.target.value, 10);
                                        if (!isNaN(value) && value > 0 && value <= 1000) {
                                            onProfilingFrequencyChange(value);
                                        }
                                    }}
                                    type="number"
                                    size="small"
                                    inputProps={{
                                        min: 1,
                                        max: 1000,
                                        style: { textAlign: 'center' }
                                    }}
                                    sx={{
                                        width: '70px',
                                        '& .MuiOutlinedInput-root': {
                                            height: '32px',
                                            fontSize: '0.875rem'
                                        }
                                    }}
                                />
                                <Typography variant="body2" sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>
                                    Hz
                                </Typography>
                            </Box>
                        </Tooltip>
                        
                        {/* Max Processes Field */}
                        <Tooltip title="Maximum number of processes to profile per runtime profiler (all profilers except perf and ebpf)">
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 5 }}>
                                <Typography variant="body2" sx={{ fontSize: '0.875rem', whiteSpace: 'nowrap' }}>
                                    Max Processes:
                                </Typography>
                                <TextField
                                    value={maxProcesses}
                                    onChange={(e) => {
                                        const value = parseInt(e.target.value, 10);
                                        if (!isNaN(value) && value >= 0 && value <= 1000) {
                                            onMaxProcessesChange(value);
                                        }
                                    }}
                                    type="number"
                                    size="small"
                                    inputProps={{
                                        min: 0,
                                        max: 1000,
                                        style: { textAlign: 'center' }
                                    }}
                                    sx={{
                                        width: '70px',
                                        '& .MuiOutlinedInput-root': {
                                            height: '32px',
                                            fontSize: '0.875rem'
                                        }
                                    }}
                                />
                                <Typography variant="body2" sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>
                                    procs
                                </Typography>
                            </Box>
                        </Tooltip>
                    </Flexbox>

                    {/* Right side - Info and Clear Filters */}
                    <Flexbox spacing={3} alignItems='center' divider={<PanelDivider />}>
                        {hasActiveFilters && (
                            <Button variant='outlined' color='secondary' size='small' onClick={clearAllFilters}>
                                Clear Filters
                            </Button>
                        )}
                        <Typography variant='body2' color='text.secondary'>
                            {rowsCount} hosts found
                        </Typography>
                    </Flexbox>
                </Flexbox>
            </Box>
            {/* Profiler Configuration Section */}
            <Box sx={{ px: 5, width: '100%' }}>
                <Accordion sx={{ boxShadow: 'none', border: '1px solid #e0e0e0' }}>
                    <AccordionSummary
                        expandIcon={<Typography sx={{ fontSize: '1.2rem' }}>▼</Typography>}
                        sx={{ 
                            backgroundColor: '#f5f5f5',
                            '& .MuiAccordionSummary-content': {
                                alignItems: 'center'
                            }
                        }}
                    >
                        <Typography variant="body2" sx={{ fontSize: '0.875rem', fontWeight: 500 }}>
                            Click for Advanced Profiler Configuration
                        </Typography>
                    </AccordionSummary>
                    <AccordionDetails sx={{ p: 3 }}>
                        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 3 }}>
                            {profilerDefinitions.map((profiler) => (
                                <Box key={profiler.key} sx={{ 
                                    border: '1px solid #e0e0e0', 
                                    borderRadius: 2, 
                                    p: 2,
                                    backgroundColor: '#fafafa'
                                }}>
                                    <Typography variant="body2" sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 0.5 }}>
                                        {profiler.name}
                                    </Typography>
                                    <Typography variant="body2" sx={{ fontSize: '0.75rem', color: 'text.secondary', mb: 2 }}>
                                        {profiler.description}
                                    </Typography>
                                    <RadioGroup
                                        value={profilerConfigs[profiler.key]}
                                        onChange={(e) => handleProfilerConfigChange(profiler.key, e.target.value)}
                                    >
                                        {profiler.options.map((option) => (
                                            <Tooltip 
                                                key={option.value} 
                                                title={option.tooltip || ''} 
                                                placement="right"
                                                arrow
                                            >
                                                <FormControlLabel
                                                    value={option.value}
                                                    control={<Radio size="small" />}
                                                    label={
                                                        <Typography variant="body2" sx={{ fontSize: '0.75rem' }}>
                                                            {option.label}
                                                        </Typography>
                                                    }
                                                    sx={{ mb: 0.5 }}
                                                />
                                            </Tooltip>
                                        ))}
                                    </RadioGroup>
                                </Box>
                            ))}
                        </Box>
                    </AccordionDetails>
                </Accordion>
            </Box>
        </Flexbox>
    );
};

export default ProfilingTopPanel;
