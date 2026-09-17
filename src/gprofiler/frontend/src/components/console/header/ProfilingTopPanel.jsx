import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    Box,
    Button,
    Checkbox,
    FormControlLabel,
    Paper,
    Radio,
    RadioGroup,
    TextField,
    Tooltip,
    Typography,
} from '@mui/material';
import React from 'react';

import Icon from '../../common/icon/Icon';
import { ICONS_NAMES } from '../../common/icon/iconsData';

const ACTION_COLORS = {
    start: { bg: '#16a34a', hover: '#15803d' },
    stop: { bg: '#dc2626', hover: '#b91c1c' },
    save: { bg: '#2563eb', hover: '#1d4ed8' },
};

const fieldSx = {
    width: '110px',
    '& .MuiOutlinedInput-root': {
        height: '36px',
        fontSize: '0.875rem',
    },
};

const Label = ({ children }) => (
    <Typography variant='body2' sx={{ fontSize: '0.875rem', fontWeight: 500, mb: 0.5 }}>
        {children}
    </Typography>
);

const Helper = ({ children }) => (
    <Typography variant='caption' sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
        {children}
    </Typography>
);

const ProfilingTopPanel = ({
    selectionModel,
    handleBulkAction,
    fetchProfilingStatus,
    filters,
    loading,
    enablePerfSpect,
    onPerfSpectChange,
    profilingFrequency,
    onProfilingFrequencyChange,
    maxProcesses,
    onMaxProcessesChange,
    profilingMode,
    onProfilingModeChange,
    duration,
    onDurationChange,
    profilerConfigs,
    onProfilerConfigsChange,
    onSaveConfiguration,
}) => {
    const selectedCount = selectionModel.length;
    const isAdhoc = profilingMode === 'adhoc';

    const handleProfilerConfigChange = (profilerKey, value) => {
        onProfilerConfigsChange((prev) => ({ ...prev, [profilerKey]: value }));
    };

    const handleAsyncProfilerConfigChange = (field, value) => {
        onProfilerConfigsChange((prev) => ({
            ...prev,
            async_profiler: { ...prev.async_profiler, [field]: value },
        }));
    };

    const handlePerfProfilerConfigChange = (field, value) => {
        onProfilerConfigsChange((prev) => ({
            ...prev,
            perf: { ...prev.perf, [field]: value },
        }));
    };

    const handlePerfEventToggle = (eventName, isChecked) => {
        const currentEvents = profilerConfigs.perf?.events || [];
        const newEvents = isChecked
            ? [...currentEvents, eventName]
            : currentEvents.filter((ev) => ev !== eventName);
        handlePerfProfilerConfigChange('events', newEvents);
    };

    const perfEvents = [
        { value: 'cpu-cycles', label: 'CPU Cycles', tooltip: 'Total processor cycles executed' },
        { value: 'instructions', label: 'Instructions', tooltip: 'Instructions executed by the CPU' },
        { value: 'cache-misses', label: 'Cache Misses', tooltip: 'Failed cache lookups - indicates memory access issues' },
        { value: 'cache-references', label: 'Cache References', tooltip: 'Total cache access attempts' },
        { value: 'branch-instructions', label: 'Branch Instructions', tooltip: 'Conditional jump instructions executed' },
        { value: 'branch-misses', label: 'Branch Misses', tooltip: 'Mispredicted branches - impacts pipeline efficiency' },
        { value: 'stalled-cycles-frontend', label: 'Stalled Cycles (Frontend)', tooltip: 'CPU cycles stalled waiting for instructions' },
        { value: 'stalled-cycles-backend', label: 'Stalled Cycles (Backend)', tooltip: 'CPU cycles stalled during execution (CPU-dependent)' },
    ];

    const profilerDefinitions = [
        {
            key: 'pyperf',
            name: 'Pyperf',
            description: "Python's highly optimized eBPF. Exception - arm64 hosts",
            options: [
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' },
            ],
        },
        {
            key: 'pyspy',
            name: 'Pyspy',
            description: 'Python',
            options: [
                { value: 'enabled_fallback', label: 'Enabled as Fallback for Pyperf' },
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' },
            ],
        },
        {
            key: 'rbspy',
            name: 'Rbspy',
            description: 'Ruby',
            options: [
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' },
            ],
        },
        {
            key: 'phpspy',
            name: 'PHPspy',
            description: 'PHP',
            options: [
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' },
            ],
        },
        {
            key: 'dotnet_trace',
            name: '.NET Trace',
            description: '.NET',
            options: [
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' },
            ],
        },
        {
            key: 'nodejs_perf',
            name: 'Perl',
            description: 'NodeJS',
            options: [
                { value: 'enabled', label: 'Enabled' },
                { value: 'disabled', label: 'Disabled' },
            ],
        },
    ];

    const profilerCardSx = {
        border: '1px solid #e0e0e0',
        borderRadius: 2,
        p: 2,
        backgroundColor: '#fff',
    };

    const clampInt = (raw, min, max) => {
        const value = parseInt(raw, 10);
        if (Number.isNaN(value)) return null;
        return Math.min(Math.max(value, min), max);
    };

    return (
        <Box sx={{ px: 4, pb: 3, display: 'flex', flexDirection: 'column', gap: 3 }}>
            {/* Basic Configuration */}
            <Paper variant='outlined' sx={{ borderRadius: 2, p: 3 }}>
                <Typography variant='subtitle1' sx={{ fontWeight: 600, mb: 3 }}>
                    Basic Configuration
                </Typography>
                <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 4 }}>
                    {/* Left column */}
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        <Tooltip title='Enable Intel PerfSpect hardware metrics collection (auto-installs on agents)'>
                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={enablePerfSpect}
                                        onChange={(e) => onPerfSpectChange(e.target.checked)}
                                        size='small'
                                        color='primary'
                                    />
                                }
                                label={
                                    <Typography variant='body2' sx={{ fontSize: '0.875rem' }}>
                                        PerfSpect HW Metrics
                                    </Typography>
                                }
                                sx={{ m: 0 }}
                            />
                        </Tooltip>

                        <Box>
                            <Label>Profiling Frequency (Hz)</Label>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <TextField
                                    value={profilingFrequency}
                                    onChange={(e) => {
                                        const value = clampInt(e.target.value, 1, 1000);
                                        if (value !== null) onProfilingFrequencyChange(value);
                                    }}
                                    type='number'
                                    size='small'
                                    inputProps={{ min: 1, max: 1000 }}
                                    sx={fieldSx}
                                />
                                <Typography variant='body2' sx={{ color: 'text.secondary' }}>
                                    Hz
                                </Typography>
                            </Box>
                            <Helper>Sampling rate (11, 49, 99, 199 Hz)</Helper>
                        </Box>

                        <Box>
                            <Label>Max Processes</Label>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <TextField
                                    value={maxProcesses}
                                    onChange={(e) => {
                                        const value = clampInt(e.target.value, 0, 1000);
                                        if (value !== null) onMaxProcessesChange(value);
                                    }}
                                    type='number'
                                    size='small'
                                    inputProps={{ min: 0, max: 1000 }}
                                    sx={fieldSx}
                                />
                                <Typography variant='body2' sx={{ color: 'text.secondary' }}>
                                    processes
                                </Typography>
                            </Box>
                        </Box>
                    </Box>

                    {/* Right column */}
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        <Box>
                            <Label>Mode</Label>
                            <RadioGroup
                                row
                                value={profilingMode}
                                onChange={(e) => onProfilingModeChange(e.target.value)}>
                                <FormControlLabel
                                    value='adhoc'
                                    control={<Radio size='small' />}
                                    label={<Typography variant='body2' sx={{ fontSize: '0.875rem' }}>Ad Hoc</Typography>}
                                />
                                <FormControlLabel
                                    value='continuous'
                                    control={<Radio size='small' />}
                                    label={<Typography variant='body2' sx={{ fontSize: '0.875rem' }}>Continuous</Typography>}
                                />
                            </RadioGroup>
                            <Helper>
                                {isAdhoc
                                    ? 'Single profiling session with specified duration'
                                    : 'Ongoing profiling (duration fixed at 60 seconds)'}
                            </Helper>
                        </Box>

                        <Box>
                            <Label>Duration</Label>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <TextField
                                    value={isAdhoc ? duration : 60}
                                    onChange={(e) => {
                                        const value = clampInt(e.target.value, 1, 3600);
                                        if (value !== null) onDurationChange(value);
                                    }}
                                    type='number'
                                    size='small'
                                    disabled={!isAdhoc}
                                    inputProps={{ min: 1, max: 3600 }}
                                    sx={{
                                        ...fieldSx,
                                        '& .MuiOutlinedInput-root': {
                                            ...fieldSx['& .MuiOutlinedInput-root'],
                                            backgroundColor: isAdhoc ? 'white' : '#f5f5f5',
                                        },
                                    }}
                                />
                                <Typography variant='body2' sx={{ color: 'text.secondary' }}>
                                    seconds
                                </Typography>
                            </Box>
                        </Box>
                    </Box>
                </Box>
            </Paper>

            {/* Advanced Profiler Configuration */}
            <Accordion variant='outlined' sx={{ borderRadius: 2, '&:before': { display: 'none' } }}>
                <AccordionSummary
                    expandIcon={<Icon name={ICONS_NAMES.ChevronDown} size={20} color='#6b7280' />}
                    sx={{ '& .MuiAccordionSummary-content': { alignItems: 'center', gap: 1 } }}>
                    <Typography variant='subtitle1' sx={{ fontWeight: 600 }}>
                        Advanced Profiler Configuration
                    </Typography>
                    <Tooltip title='Configure per-language profilers used during the profiling session'>
                        <Box
                            sx={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                width: 16,
                                height: 16,
                                borderRadius: '50%',
                                border: '1px solid #9ca3af',
                                color: '#6b7280',
                                fontSize: '0.7rem',
                            }}>
                            i
                        </Box>
                    </Tooltip>
                </AccordionSummary>
                <AccordionDetails sx={{ p: 3, pt: 0 }}>
                    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 3 }}>
                        {/* Perf Profiler */}
                        <Box sx={profilerCardSx}>
                            <Typography variant='body2' sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 0.5 }}>
                                Perf Profiler
                            </Typography>
                            <Typography variant='body2' sx={{ fontSize: '0.75rem', color: 'text.secondary', mb: 2 }}>
                                C, C++, Go, Kernel
                            </Typography>
                            <RadioGroup
                                value={profilerConfigs.perf?.mode || 'enabled_restricted'}
                                onChange={(e) => handlePerfProfilerConfigChange('mode', e.target.value)}>
                                <Tooltip title='Profiles only top N containers/process' placement='right' arrow>
                                    <FormControlLabel
                                        value='enabled_restricted'
                                        control={<Radio size='small' />}
                                        label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Enabled Restricted</Typography>}
                                        sx={{ mb: 0.5 }}
                                    />
                                </Tooltip>
                                <Tooltip title='Profiles all processes' placement='right' arrow>
                                    <FormControlLabel
                                        value='enabled_aggressive'
                                        control={<Radio size='small' />}
                                        label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Enabled Aggressive</Typography>}
                                        sx={{ mb: 0.5 }}
                                    />
                                </Tooltip>
                                <FormControlLabel
                                    value='disabled'
                                    control={<Radio size='small' />}
                                    label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Disabled</Typography>}
                                    sx={{ mb: 0.5 }}
                                />
                            </RadioGroup>

                            {profilerConfigs.perf?.mode !== 'disabled' && (
                                <Box sx={{ ml: 3, mt: 2 }}>
                                    <Typography variant='body2' sx={{ fontSize: '0.75rem', fontWeight: 500, mb: 1 }}>
                                        Event Types (select one or more):
                                    </Typography>
                                    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                                        {perfEvents.map((event) => (
                                            <Tooltip key={event.value} title={event.tooltip} placement='right' arrow>
                                                <FormControlLabel
                                                    control={
                                                        <Checkbox
                                                            checked={profilerConfigs.perf?.events?.includes(event.value) || false}
                                                            onChange={(e) => handlePerfEventToggle(event.value, e.target.checked)}
                                                            size='small'
                                                        />
                                                    }
                                                    label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>{event.label}</Typography>}
                                                    sx={{ mb: 0.5 }}
                                                />
                                            </Tooltip>
                                        ))}
                                    </Box>
                                </Box>
                            )}
                        </Box>

                        {/* Async Profiler */}
                        <Box sx={profilerCardSx}>
                            <Typography variant='body2' sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 0.5 }}>
                                Async Profiler
                            </Typography>
                            <Typography variant='body2' sx={{ fontSize: '0.75rem', color: 'text.secondary', mb: 2 }}>
                                Java
                            </Typography>
                            <FormControlLabel
                                control={
                                    <Checkbox
                                        checked={profilerConfigs.async_profiler?.enabled || false}
                                        onChange={(e) => handleAsyncProfilerConfigChange('enabled', e.target.checked)}
                                        size='small'
                                    />
                                }
                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Enabled</Typography>}
                                sx={{ mb: 1 }}
                            />
                            {profilerConfigs.async_profiler?.enabled && (
                                <Box sx={{ ml: 3 }}>
                                    <Typography variant='body2' sx={{ fontSize: '0.75rem', fontWeight: 500, mb: 1 }}>
                                        Time Mode:
                                    </Typography>
                                    <RadioGroup
                                        value={profilerConfigs.async_profiler?.time || 'cpu'}
                                        onChange={(e) => handleAsyncProfilerConfigChange('time', e.target.value)}>
                                        <Tooltip title='CPU time profiling - only when thread is running' placement='right' arrow>
                                            <FormControlLabel
                                                value='cpu'
                                                control={<Radio size='small' />}
                                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>CPU Time</Typography>}
                                                sx={{ mb: 0.5 }}
                                            />
                                        </Tooltip>
                                        <Tooltip title='Interval timer profiling - uses OS timer, lower overhead than CPU mode' placement='right' arrow>
                                            <FormControlLabel
                                                value='itimer'
                                                control={<Radio size='small' />}
                                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>ITimer</Typography>}
                                                sx={{ mb: 0.5 }}
                                            />
                                        </Tooltip>
                                        <Tooltip title='Wall clock time profiling - includes waiting/blocking time' placement='right' arrow>
                                            <FormControlLabel
                                                value='wall'
                                                control={<Radio size='small' />}
                                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Wall Time</Typography>}
                                                sx={{ mb: 0.5 }}
                                            />
                                        </Tooltip>
                                        <Tooltip title='Auto mode - resolves to CPU or ITimer at runtime based on host capabilities' placement='right' arrow>
                                            <FormControlLabel
                                                value='auto'
                                                control={<Radio size='small' />}
                                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Auto</Typography>}
                                                sx={{ mb: 0.5 }}
                                            />
                                        </Tooltip>
                                        <Tooltip title='Allocation profiling - samples on memory allocations instead of time' placement='right' arrow>
                                            <FormControlLabel
                                                value='alloc'
                                                control={<Radio size='small' />}
                                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>Allocation</Typography>}
                                                sx={{ mb: 0.5 }}
                                            />
                                        </Tooltip>
                                    </RadioGroup>
                                    {profilerConfigs.async_profiler?.time === 'alloc' && (
                                        <Box sx={{ mt: 1 }}>
                                            <Typography variant='body2' sx={{ fontSize: '0.75rem', fontWeight: 500, mb: 0.5 }}>
                                                Allocation Interval:
                                            </Typography>
                                            <Tooltip
                                                title="Allocation interval between heap samples. Use bitmath unit notation: MB, KiB, GiB, etc. (e.g. '2MB', '512KiB')"
                                                placement='right'
                                                arrow>
                                                <input
                                                    type='text'
                                                    value={profilerConfigs.async_profiler?.alloc_interval ?? ''}
                                                    onChange={(e) => handleAsyncProfilerConfigChange('alloc_interval', e.target.value)}
                                                    placeholder='e.g. 2MB, 512KiB'
                                                    style={{
                                                        fontSize: '0.75rem',
                                                        padding: '4px 8px',
                                                        border: '1px solid #ccc',
                                                        borderRadius: '4px',
                                                        width: '120px',
                                                    }}
                                                />
                                            </Tooltip>
                                        </Box>
                                    )}
                                </Box>
                            )}
                        </Box>

                        {/* Remaining language profilers */}
                        {profilerDefinitions.map((profiler) => (
                            <Box key={profiler.key} sx={profilerCardSx}>
                                <Typography variant='body2' sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 0.5 }}>
                                    {profiler.name}
                                </Typography>
                                <Typography variant='body2' sx={{ fontSize: '0.75rem', color: 'text.secondary', mb: 2 }}>
                                    {profiler.description}
                                </Typography>
                                <RadioGroup
                                    value={profilerConfigs[profiler.key]}
                                    onChange={(e) => handleProfilerConfigChange(profiler.key, e.target.value)}>
                                    {profiler.options.map((option) => (
                                        <Tooltip key={option.value} title={option.tooltip || ''} placement='right' arrow>
                                            <FormControlLabel
                                                value={option.value}
                                                control={<Radio size='small' />}
                                                label={<Typography variant='body2' sx={{ fontSize: '0.75rem' }}>{option.label}</Typography>}
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

            {/* Action bar */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                <Button
                    variant='contained'
                    size='medium'
                    onClick={() => handleBulkAction('start')}
                    disabled={selectedCount === 0}
                    startIcon={<Box component='span' sx={{ fontSize: '0.7rem' }}>▶</Box>}
                    sx={{
                        backgroundColor: ACTION_COLORS.start.bg,
                        '&:hover': { backgroundColor: ACTION_COLORS.start.hover },
                    }}>
                    {`Start Profiling${selectedCount ? ` (${selectedCount})` : ''}`}
                </Button>
                <Button
                    variant='contained'
                    size='medium'
                    onClick={() => handleBulkAction('stop')}
                    disabled={selectedCount === 0}
                    startIcon={<Box component='span' sx={{ fontSize: '0.7rem' }}>■</Box>}
                    sx={{
                        backgroundColor: ACTION_COLORS.stop.bg,
                        '&:hover': { backgroundColor: ACTION_COLORS.stop.hover },
                    }}>
                    {`Stop Profiling${selectedCount ? ` (${selectedCount})` : ''}`}
                </Button>
                <Button
                    variant='outlined'
                    color='inherit'
                    size='medium'
                    onClick={() => fetchProfilingStatus(filters)}
                    disabled={loading}
                    startIcon={<Icon name={ICONS_NAMES.Refresh} size={18} color='#6b7280' />}>
                    Refresh
                </Button>
                <Box sx={{ flexGrow: 1 }} />
                <Button
                    variant='contained'
                    size='medium'
                    onClick={onSaveConfiguration}
                    sx={{
                        backgroundColor: ACTION_COLORS.save.bg,
                        '&:hover': { backgroundColor: ACTION_COLORS.save.hover },
                    }}>
                    Save Configuration
                </Button>
            </Box>
        </Box>
    );
};

export default ProfilingTopPanel;
