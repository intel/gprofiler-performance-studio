import { 
    Box, 
    Typography, 
    Dialog, 
    DialogTitle, 
    DialogContent, 
    DialogActions, 
    Button, 
    Divider, 
    Chip 
} from '@mui/material';
import queryString from 'query-string';
import React, { useCallback, useEffect, useState } from 'react';
import { useHistory, useLocation } from 'react-router-dom';

import { DATA_URLS } from '../../api/urls';
import { PAGES } from '../../utils/consts';
import MuiTable from '../common/dataDisplay/table/MuiTable';
import PageHeader from '../common/layout/PageHeader';
import ProfilingHeader from './header/ProfilingHeader';
import ProfilingTopPanel from './header/ProfilingTopPanel';

const columns = [
    { field: 'service', headerName: 'service name', flex: 1, sortable: true },
    { field: 'host', headerName: 'host name', flex: 1, sortable: true },
    { field: 'pids', headerName: 'pids (if profiled)', flex: 1, sortable: true },
    { field: 'ip', headerName: 'IP', flex: 1, sortable: true },
    { field: 'commandType', headerName: 'command type', flex: 1, sortable: true },
    { field: 'status', headerName: 'profiling status', flex: 1, sortable: true },
    {
        field: 'heartbeat_timestamp',
        headerName: 'last heartbeat',
        flex: 1,
        sortable: true,
        renderCell: (params) => {
            if (!params.value) return 'N/A';
            try {
                // The backend sends UTC timestamp without 'Z' suffix, so we need to explicitly treat it as UTC
                let utcTimestamp = params.value;
                if (!utcTimestamp.endsWith('Z') && !utcTimestamp.includes('+') && !utcTimestamp.includes('-', 10)) {
                    utcTimestamp += 'Z';
                }

                const utcDate = new Date(utcTimestamp);
                // Convert to user's local timezone
                const localDateTimeString = utcDate.toLocaleString(navigator.language, {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: true,
                });
                return localDateTimeString;
            } catch (error) {
                return 'Invalid date';
            }
        },
    },
    {
        field: 'profile',
        headerName: 'profile',
        flex: 1,
        renderCell: (params) => {
            const { host, service, commandType, status } = params.row;
            
            // Only show profile link for rows with commandType="start" and status="completed"
            if (commandType !== 'start' || status !== 'completed') {
                return '';
            }
            
            if (!host || !service) return '';
            
            const baseUrl = `${window.location.protocol}//${window.location.host}`;
            const profileUrl = `${baseUrl}${PAGES.profiles.to}?filter=hn,is,${encodeURIComponent(host)}&gtab=1&pm=1&rtms=1&service=${encodeURIComponent(service)}&time=1h&view=flamegraph&wp=100`;
            
            return (
                <a
                    href={profileUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#1976d2', textDecoration: 'none' }}
                    onMouseOver={(e) => e.target.style.textDecoration = 'underline'}
                    onMouseOut={(e) => e.target.style.textDecoration = 'none'}
                >
                    View Profile
                </a>
            );
        },
    },
];

const ProfilingStatusPage = () => {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selectionModel, setSelectionModel] = useState([]);
    const [filters, setFilters] = useState({
        service: '',
        hostname: '',
        pids: '',
        ip: '',
        commandType: '',
        status: '',
    });
    const [appliedFilters, setAppliedFilters] = useState({
        service: '',
        hostname: '',
        pids: '',
        ip: '',
        commandType: '',
        status: '',
    });
    
    // PerfSpect state
    const [enablePerfSpect, setEnablePerfSpect] = useState(false);
    
    // Profiling frequency state
    const [profilingFrequency, setProfilingFrequency] = useState(11);
    
    // Max processes state
    const [maxProcesses, setMaxProcesses] = useState(10);
    
    // Profiler configurations state
    const [profilerConfigs, setProfilerConfigs] = useState({
        perf: 'enabled_restricted', // 'enabled_restricted', 'enabled_aggressive', 'disabled'
        async_profiler: 'enabled', // 'enabled', 'disabled'
        pyperf: 'enabled', // 'enabled', 'disabled'
        pyspy: 'enabled_fallback', // 'enabled_fallback', 'enabled', 'disabled'
        rbspy: 'enabled', // 'enabled', 'disabled'
        phpspy: 'enabled', // 'enabled', 'disabled'
        dotnet_trace: 'enabled', // 'enabled', 'disabled'
        nodejs_perf: 'enabled', // 'enabled', 'disabled'
    });

    // Confirmation dialog state
    const [confirmationDialog, setConfirmationDialog] = useState({
        open: false,
        action: null,
        selectedRows: [],
        serviceGroups: {},
    });
    
    const history = useHistory();
    const location = useLocation();

    const fetchProfilingStatus = useCallback((filterParams) => {
        setLoading(true);

        // Build query parameters
        const params = new URLSearchParams();

        if (filterParams.service) {
            params.append('service_name', filterParams.service);
        }
        if (filterParams.hostname) {
            params.append('hostname', filterParams.hostname);
        }
        if (filterParams.pids) {
            params.append('pids', filterParams.pids);
        }
        if (filterParams.ip) {
            params.append('ip_address', filterParams.ip);
        }
        if (filterParams.commandType) {
            params.append('command_type', filterParams.commandType);
        }
        if (filterParams.status) {
            params.append('profiling_status', filterParams.status);
        }

        const url = params.toString()
            ? `${DATA_URLS.GET_PROFILING_HOST_STATUS}?${params.toString()}`
            : DATA_URLS.GET_PROFILING_HOST_STATUS;

        fetch(url)
            .then((res) => res.json())
            .then((data) => {
                setRows(
                    data.map((row) => ({
                        id: row.id,
                        service: row.service_name,
                        host: row.hostname,
                        pids: row.pids,
                        ip: row.ip_address,
                        commandType: row.command_type || 'N/A',
                        status: row.profiling_status,
                        heartbeat_timestamp: row.heartbeat_timestamp,
                    }))
                );
                setLoading(false);
            })
            .catch(() => setLoading(false));
    }, []); // No dependencies needed since it takes filterParams as argument

    // Initialize filters from URL parameters for direct URL visits (shareable links)
    useEffect(() => {
        const searchParams = queryString.parse(location.search);
        const hasFilterParams = ['service', 'hostname', 'pids', 'ip', 'commandType', 'status'].some(
            param => searchParams[param]
        );
        
        // Only initialize from URL if there are actual filter parameters
        if (hasFilterParams) {
            const urlFilters = {
                service: searchParams.service || '',
                hostname: searchParams.hostname || '',
                pids: searchParams.pids || '',
                ip: searchParams.ip || '',
                commandType: searchParams.commandType || '',
                status: searchParams.status || '',
            };
            setFilters(urlFilters);
            setAppliedFilters(urlFilters);
            // Automatically fetch data with URL filters on page load
            fetchProfilingStatus(urlFilters);
        } else {
            // No URL params, fetch all data
            const emptyFilters = {
                service: '',
                hostname: '',
                pids: '',
                ip: '',
                commandType: '',
                status: '',
            };
            fetchProfilingStatus(emptyFilters);
        }
        
        // Clean up profile-specific parameters if they exist (mixed URLs)
        const profileParams = ['gtab', 'view', 'time', 'startTime', 'endTime', 'filter', 'rt', 'rtms', 'p', 'pm', 'wt', 'wp', 'search', 'fullscreen'];
        const hasProfileParams = profileParams.some(param => searchParams[param]);
        
        if (hasProfileParams) {
            // Remove only profile params, keep filter params
            const cleanedParams = { ...searchParams };
            profileParams.forEach(param => {
                delete cleanedParams[param];
            });
            history.replace({ search: queryString.stringify(cleanedParams) });
        }
    }, [fetchProfilingStatus, history, location.search]); // Add dependencies

    // Auto-refresh every 30 seconds for dynamic profiling
    useEffect(() => {
        const refreshInterval = setInterval(() => {
            // Refresh with current applied filters
            fetchProfilingStatus(appliedFilters);
        }, 30000); // 30 seconds

        // Cleanup interval on component unmount
        return () => clearInterval(refreshInterval);
    }, [appliedFilters, fetchProfilingStatus]); // Re-create interval when filters change

    // Update URL when filters change (with focus preservation)
    const updateURL = useCallback(
        (newFilters) => {
            // Use replace instead of push to avoid navigation history buildup
            // and reduce re-render impact on focus
            const searchParams = {};

            // Add new filter parameters
            Object.keys(newFilters).forEach((key) => {
                if (newFilters[key]) {
                    searchParams[key] = newFilters[key];
                }
            });

            const newSearch = queryString.stringify(searchParams);
            
            // Use replace instead of push to minimize focus disruption
            if (newSearch === '') {
                history.replace('/profiling');
            } else {
                history.replace({ pathname: '/profiling', search: newSearch });
            }
        },
        [history]
    );

    // Function to update individual filter (optimized for focus preservation)
    const updateFilter = useCallback((field, value) => {
        setFilters(prev => ({ ...prev, [field]: value }));
    }, []); // Stable function reference

    // Apply filters function
    const applyFilters = useCallback(() => {
        setAppliedFilters(filters);
        fetchProfilingStatus(filters);
        updateURL(filters);
    }, [filters, fetchProfilingStatus, updateURL]);

    // Clear all filters function
    const clearAllFilters = useCallback(() => {
        const emptyFilters = {
            service: '',
            hostname: '',
            pids: '',
            ip: '',
            commandType: '',
            status: '',
        };
        setFilters(emptyFilters);
        setAppliedFilters(emptyFilters);
        fetchProfilingStatus(emptyFilters);
        updateURL(emptyFilters);
    }, [fetchProfilingStatus, updateURL]);

    // Bulk Start/Stop handlers
    function handleBulkAction(action) {
        const selectedRows = rows.filter((row) => selectionModel.includes(row.id));

        // Group selected rows by service name
        const serviceGroups = selectedRows.reduce((groups, row) => {
            if (!groups[row.service]) {
                groups[row.service] = [];
            }
            groups[row.service].push(row.host);
            return groups;
        }, {});

        // Show confirmation dialog
        setConfirmationDialog({
            open: true,
            action,
            selectedRows,
            serviceGroups,
        });
    }

    // Execute the actual profiling action after confirmation
    function executeProfilingAction() {
        const { action, serviceGroups } = confirmationDialog;

        // Create one request per service with all hosts for that service
        const requests = Object.entries(serviceGroups).map(([serviceName, hosts]) => {
            const target_host = hosts.reduce((hostObj, host) => {
                hostObj[host] = null;
                return hostObj;
            }, {});

            const submitData = {
                service_name: serviceName,
                request_type: action,
                continuous: true,
                duration: 60, // Default duration, can't be adjusted yet
                frequency: profilingFrequency, // Use frequency from UI
                profiling_mode: 'cpu', // Default profiling mode, can't be adjusted yet
                target_hosts: target_host,
                additional_args: {
                    enable_perfspect: enablePerfSpect, // Include PerfSpect setting
                    profiler_configs: profilerConfigs, // Include all profiler configurations
                    max_processes: maxProcesses, // Include max processes setting
                },
            };

            // append 'stop_level: host' when action is 'stop'
            if (action === 'stop') {
                submitData.stop_level = 'host';
            }

            return fetch(DATA_URLS.POST_PROFILING_REQUEST, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(submitData),
            });
        });

        // Close dialog and wait for all requests to finish before refreshing
        setConfirmationDialog({ open: false, action: null, selectedRows: [], serviceGroups: {} });
        Promise.all(requests).then(() => {
            // Maintain current filter state when refreshing
            fetchProfilingStatus(appliedFilters);
            setSelectionModel([]); // Clear all checkboxes after API requests complete
            setEnablePerfSpect(false); // Reset PerfSpect checkbox after action completes
            // Note: Keep profiling frequency as is - user may want to reuse the same frequency
        });
    }

    // Close confirmation dialog without action
    function handleDialogClose() {
        setConfirmationDialog({ open: false, action: null, selectedRows: [], serviceGroups: {} });
    }

    return (
        <Box sx={{ backgroundColor: 'white.main', height: '100%' }}>
            <ProfilingHeader 
                filters={filters} 
                updateFilter={updateFilter} 
                isLoading={loading}
                onApplyFilters={applyFilters}
                onClearFilters={clearAllFilters}
            />

            <Box
                sx={{
                    display: 'flex',
                    flexDirection: 'column',
                }}>
                <ProfilingTopPanel
                    selectionModel={selectionModel}
                    handleBulkAction={handleBulkAction}
                    fetchProfilingStatus={fetchProfilingStatus}
                    filters={appliedFilters}
                    loading={loading}
                    rowsCount={rows.length}
                    clearAllFilters={clearAllFilters}
                    enablePerfSpect={enablePerfSpect}
                    onPerfSpectChange={setEnablePerfSpect}
                    profilingFrequency={profilingFrequency}
                    onProfilingFrequencyChange={setProfilingFrequency}
                    maxProcesses={maxProcesses}
                    onMaxProcessesChange={setMaxProcesses}
                    profilerConfigs={profilerConfigs}
                    onProfilerConfigsChange={setProfilerConfigs}
                />

                {/* Data Table */}
                <Box sx={{ p: 4, '& .MuiDataGrid-root': { border: 'none' } }}>
                    <MuiTable
                        columns={columns}
                        data={rows}
                        isLoading={loading}
                        pageSize={50}
                        rowHeight={50}
                        autoPageSize
                        checkboxSelection
                        onSelectionModelChange={setSelectionModel}
                        selectionModel={selectionModel}
                        initialState={{
                            sorting: {
                                sortModel: [{ field: 'host', sort: 'asc' }],
                            },
                        }}
                    />
                </Box>
            </Box>

            {/* Confirmation Dialog */}
            <Dialog
                open={confirmationDialog.open}
                onClose={handleDialogClose}
                maxWidth="md"
                fullWidth
            >
                <DialogTitle>
                    <Typography variant="h6" component="div">
                        Confirm {confirmationDialog.action === 'start' ? 'Start' : 'Stop'} Profiling
                    </Typography>
                </DialogTitle>
                <DialogContent>
                    <Typography variant="body1" sx={{ mb: 2 }}>
                        Are you sure you want to <strong>{confirmationDialog.action}</strong> profiling for the following hosts?
                    </Typography>
                    
                    {/* Selected Hosts Summary */}
                    <Box sx={{ mb: 3 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                            Selected Hosts ({confirmationDialog.selectedRows.length}):
                        </Typography>
                        {Object.entries(confirmationDialog.serviceGroups).map(([serviceName, hosts]) => (
                            <Box key={serviceName} sx={{ mb: 1 }}>
                                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                    {serviceName}:
                                </Typography>
                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                                    {hosts.map((host) => (
                                        <Chip
                                            key={host}
                                            label={host}
                                            size="small"
                                            variant="outlined"
                                        />
                                    ))}
                                </Box>
                            </Box>
                        ))}
                    </Box>

                    {/* Configuration Summary (only for start action) */}
                    {confirmationDialog.action === 'start' && (
                        <>
                            <Divider sx={{ my: 2 }} />
                            <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
                                Profiling Configuration:
                            </Typography>
                            
                            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                                {/* Basic Settings */}
                                <Box>
                                    <Typography variant="body2" sx={{ fontWeight: 500, mb: 1 }}>
                                        Basic Settings:
                                    </Typography>
                                    <Typography variant="body2">• Frequency: {profilingFrequency} Hz</Typography>
                                    <Typography variant="body2">• Max Processes: {maxProcesses}</Typography>
                                    <Typography variant="body2">• PerfSpect HW Metrics: {enablePerfSpect ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• Duration: 60 seconds</Typography>
                                    <Typography variant="body2">• Mode: CPU profiling</Typography>
                                </Box>

                                {/* Profiler Settings */}
                                <Box>
                                    <Typography variant="body2" sx={{ fontWeight: 500, mb: 1 }}>
                                        Profiler Settings:
                                    </Typography>
                                    <Typography variant="body2">• Perf (C/C++/Go): {
                                        profilerConfigs.perf === 'enabled_restricted' ? 'Enabled (Restricted)' :
                                        profilerConfigs.perf === 'enabled_aggressive' ? 'Enabled (Aggressive)' : 'Disabled'
                                    }</Typography>
                                    <Typography variant="body2">• Java Async Profiler: {profilerConfigs.async_profiler === 'enabled' ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• Pyperf (Python): {profilerConfigs.pyperf === 'enabled' ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• Pyspy (Python): {
                                        profilerConfigs.pyspy === 'enabled_fallback' ? 'Enabled (Fallback)' :
                                        profilerConfigs.pyspy === 'enabled' ? 'Enabled' : 'Disabled'
                                    }</Typography>
                                    <Typography variant="body2">• Rbspy (Ruby): {profilerConfigs.rbspy === 'enabled' ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• PHPspy (PHP): {profilerConfigs.phpspy === 'enabled' ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• .NET Trace: {profilerConfigs.dotnet_trace === 'enabled' ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• NodeJS Perf: {profilerConfigs.nodejs_perf === 'enabled' ? 'Enabled' : 'Disabled'}</Typography>
                                </Box>
                            </Box>
                        </>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleDialogClose} color="primary">
                        Cancel
                    </Button>
                    <Button 
                        onClick={executeProfilingAction} 
                        color={confirmationDialog.action === 'start' ? 'success' : 'error'}
                        variant="contained"
                    >
                        {confirmationDialog.action === 'start' ? 'Start Profiling' : 'Stop Profiling'}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ProfilingStatusPage;
