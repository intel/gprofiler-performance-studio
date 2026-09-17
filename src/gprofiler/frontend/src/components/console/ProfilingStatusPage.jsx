import {
    Alert,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    Snackbar,
    Tab,
    Tabs,
    Typography,
} from '@mui/material';
import queryString from 'query-string';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useHistory, useLocation } from 'react-router-dom';

import { DATA_URLS } from '../../api/urls';
import { PAGES } from '../../utils/consts';
import Icon from '../common/icon/Icon';
import { ICONS_NAMES } from '../common/icon/iconsData';
import MuiTable from '../common/dataDisplay/table/MuiTable';
import ProfilingHeader from './header/ProfilingHeader';
import ProfilingTopPanel from './header/ProfilingTopPanel';
import { buildProfilingRequests } from './profilingRequestBuilder.mjs';

const DEFAULT_PROFILING_FREQUENCY = 11;
const DEFAULT_MAX_PROCESSES = 10;
const DEFAULT_DURATION = 60;
const CONFIG_STORAGE_KEY = 'gprofiler.adhocProfilingConfig';

const SCOPES = [
    { id: 'service', label: 'Services' },
    { id: 'namespace', label: 'Namespaces' },
    { id: 'host', label: 'Hosts' },
    { id: 'pod', label: 'Pods' },
    { id: 'container', label: 'Containers' },
    { id: 'process', label: 'Processes' },
];

const EMPTY_FILTERS = {
    service: '',
    hostname: '',
    pids: '',
    ip: '',
    namespace: '',
    podName: '',
    containerName: '',
    processName: '',
    commandType: '',
    status: '',
};

const DEFAULT_PAGE_SIZE = 50;
const AUTO_REFRESH_INTERVAL_MS = 30000;

// DataGrid column field (camelCase) -> backend sort_by key (snake_case). Only
// mapped fields are sent; anything else is ignored (backend also whitelists).
const SORT_FIELD_MAP = {
    service: 'service_name',
    hostname: 'hostname',
    namespace: 'namespace',
    podName: 'pod_name',
    containerName: 'container_name',
    workloadName: 'workload_name',
    processName: 'process_name',
    pid: 'pid',
    heartbeatTimestamp: 'heartbeat_timestamp',
    profilingStatus: 'profiling_status',
    agentVersion: 'agent_version',
    hostCount: 'host_count',
    namespaceCount: 'namespace_count',
    podCount: 'pod_count',
    containerCount: 'container_count',
    processCount: 'process_count',
};

const readField = (row, camelKey, snakeKey = camelKey) => row[camelKey] ?? row[snakeKey];

const formatHeartbeat = (value) => {
    if (!value) {
        return 'N/A';
    }

    try {
        let utcTimestamp = value;
        if (!utcTimestamp.endsWith('Z') && !utcTimestamp.includes('+') && !utcTimestamp.includes('-', 10)) {
            utcTimestamp += 'Z';
        }
        return new Date(utcTimestamp).toLocaleString(navigator.language, {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true,
        });
    } catch (error) {
        return 'Invalid date';
    }
};

// Build a profiles-view deep link for a status row. Each scope maps to the
// filters the profiles view supports: the exact `service` param, exact Host name
// (hn,is), a "Contains" Container name match (cn,has) that joins the available
// container/deployment/namespace parts, and an exact process for the process scope.
const buildScopeProfileUrl = (row, scope, view) => {
    const baseUrl = `${window.location.protocol}//${window.location.host}`;
    const params = { gtab: '1', pm: '1', rtms: '1', time: '1h', wp: '100', service: row.service, view };
    const rules = [];
    const namespace = row.namespace || '';
    const deployment = row.workloadName || '';
    const container = row.containerName || '';
    // Join only the available parts with "_" (skip empties to avoid "__").
    const containsValue = (parts) => parts.filter(Boolean).join('_');

    if (scope === 'namespace') {
        const value = containsValue([namespace]);
        if (value) rules.push(`cn,has,${value}`);
    } else if (scope === 'host') {
        if (row.host) rules.push(`hn,is,${row.host}`);
    } else if (scope === 'pod') {
        if (row.host) rules.push(`hn,is,${row.host}`);
        const value = containsValue([deployment, namespace]);
        if (value) rules.push(`cn,has,${value}`);
    } else if (scope === 'container') {
        if (row.host) rules.push(`hn,is,${row.host}`);
        const value = containsValue([container, deployment, namespace]);
        if (value) rules.push(`cn,has,${value}`);
    } else if (scope === 'process') {
        if (row.host) rules.push(`hn,is,${row.host}`);
        // Flamegraph process nodes use the 15-char kernel comm, so match that prefix.
        if (row.processName) params.p = row.processName.slice(0, 15);
    }
    // service scope: exact service via the `service` param only, no RQL rule.
    if (rules.length) {
        params.filter = rules.join(',a,'); // ",a," is the profiles-view AND separator
    }
    return `${baseUrl}${PAGES.profiles.to}?${new URLSearchParams(params).toString()}`;
};

const makeProfileColumn = (scope) => ({
    field: 'profile',
    headerName: 'profile',
    flex: 1.2,
    sortable: false,
    renderCell: (params) => {
        const { service, profilingStatus } = params.row;
        if (!service || profilingStatus !== 'active') {
            return '';
        }

        return (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                <a href={buildScopeProfileUrl(params.row, scope, 'flamegraph')} target="_blank" rel="noopener noreferrer">
                    View Continuous Profile
                </a>
                <a href={buildScopeProfileUrl(params.row, scope, 'adhoc')} target="_blank" rel="noopener noreferrer">
                    View Adhoc Profile
                </a>
            </Box>
        );
    },
});

const getScopeColumns = (scope) => {
    const sharedTimestampColumn = {
        field: 'heartbeatTimestamp',
        headerName: 'last heartbeat',
        flex: 1,
        sortable: true,
        renderCell: (params) => formatHeartbeat(params.value),
    };
    const sharedStatusColumns = [
        { field: 'profilingStatus', headerName: 'profiling', flex: 1, sortable: true },
        { field: 'profilingMode', headerName: 'mode', flex: 1, sortable: true },
        { field: 'profilerSummary', headerName: 'profilers', flex: 1.3, sortable: false },
        { field: 'frequency', headerName: 'frequency', flex: 0.8, sortable: true },
    ];

    if (scope === 'service') {
        return [
            { field: 'service', headerName: 'service name', flex: 1.4, sortable: true },
            { field: 'namespaceCount', headerName: 'namespaces', flex: 0.8, sortable: true },
            { field: 'hostCount', headerName: 'hosts', flex: 0.7, sortable: true },
            { field: 'podCount', headerName: 'pods', flex: 0.7, sortable: true },
            { field: 'containerCount', headerName: 'containers', flex: 0.8, sortable: true },
            { field: 'processCount', headerName: 'processes', flex: 0.8, sortable: true },
            ...sharedStatusColumns,
            sharedTimestampColumn,
            { field: 'agentVersion', headerName: 'version', flex: 0.8, sortable: true },
            makeProfileColumn('service'),
        ];
    }

    if (scope === 'namespace') {
        return [
            { field: 'namespace', headerName: 'namespace', flex: 1, sortable: true },
            { field: 'service', headerName: 'service name', flex: 1.2, sortable: true },
            { field: 'hostCount', headerName: 'hosts', flex: 0.7, sortable: true },
            { field: 'podCount', headerName: 'pods', flex: 0.7, sortable: true },
            { field: 'containerCount', headerName: 'containers', flex: 0.8, sortable: true },
            { field: 'processCount', headerName: 'processes', flex: 0.8, sortable: true },
            ...sharedStatusColumns,
            sharedTimestampColumn,
            makeProfileColumn('namespace'),
        ];
    }

    if (scope === 'host') {
        return [
            { field: 'host', headerName: 'host name', flex: 1.1, sortable: true },
            { field: 'service', headerName: 'service name', flex: 1, sortable: true },
            { field: 'namespace', headerName: 'namespace', flex: 0.9, sortable: true },
            { field: 'pids', headerName: 'pids (if profiled)', flex: 1, sortable: false },
            { field: 'ip', headerName: 'IP', flex: 0.9, sortable: true },
            { field: 'commandType', headerName: 'command type', flex: 0.8, sortable: true },
            { field: 'profilingStatus', headerName: 'profiling status', flex: 0.9, sortable: true },
            sharedTimestampColumn,
            makeProfileColumn('host'),
        ];
    }

    if (scope === 'pod') {
        return [
            { field: 'podName', headerName: 'pod', flex: 1.2, sortable: true },
            { field: 'namespace', headerName: 'namespace', flex: 0.9, sortable: true },
            { field: 'service', headerName: 'service name', flex: 1, sortable: true },
            { field: 'hostCount', headerName: 'hosts', flex: 0.7, sortable: true },
            { field: 'containerCount', headerName: 'containers', flex: 0.8, sortable: true },
            { field: 'processCount', headerName: 'processes', flex: 0.8, sortable: true },
            ...sharedStatusColumns,
            sharedTimestampColumn,
            makeProfileColumn('pod'),
        ];
    }

    if (scope === 'container') {
        return [
            { field: 'containerName', headerName: 'container', flex: 1.1, sortable: true },
            { field: 'podName', headerName: 'pod', flex: 1, sortable: true },
            { field: 'namespace', headerName: 'namespace', flex: 0.9, sortable: true },
            { field: 'host', headerName: 'host', flex: 1, sortable: true },
            { field: 'processCount', headerName: 'processes', flex: 0.8, sortable: true },
            ...sharedStatusColumns,
            sharedTimestampColumn,
            makeProfileColumn('container'),
        ];
    }

    return [
        { field: 'processName', headerName: 'process', flex: 1.1, sortable: true },
        { field: 'pid', headerName: 'pid', flex: 0.6, sortable: true },
        { field: 'containerName', headerName: 'container', flex: 1, sortable: true },
        { field: 'podName', headerName: 'pod', flex: 1, sortable: true },
        { field: 'namespace', headerName: 'namespace', flex: 0.9, sortable: true },
        { field: 'host', headerName: 'host', flex: 1, sortable: true },
        ...sharedStatusColumns,
        sharedTimestampColumn,
        makeProfileColumn('process'),
    ];
};

const formatRowForScope = (row, scope) => ({
    id: readField(row, 'id'),
    scope,
    service: readField(row, 'serviceName', 'service_name'),
    namespace: readField(row, 'namespace'),
    host: readField(row, 'hostname'),
    ip: readField(row, 'ipAddress', 'ip_address'),
    podName: readField(row, 'podName', 'pod_name'),
    containerName: readField(row, 'containerName', 'container_name'),
    workloadName: readField(row, 'workloadName', 'workload_name'),
    workloadKind: readField(row, 'workloadKind', 'workload_kind'),
    processName: readField(row, 'processName', 'process_name'),
    pid: readField(row, 'pid'),
    pids: readField(row, 'pids', 'pids') || [],
    activeHosts: readField(row, 'activeHosts', 'active_hosts'),
    hostCount: readField(row, 'hostCount', 'host_count'),
    namespaceCount: readField(row, 'namespaceCount', 'namespace_count'),
    podCount: readField(row, 'podCount', 'pod_count'),
    containerCount: readField(row, 'containerCount', 'container_count'),
    processCount: readField(row, 'processCount', 'process_count'),
    commandType: readField(row, 'commandType', 'command_type') || 'N/A',
    profilingStatus: readField(row, 'profilingStatus', 'profiling_status') || 'stopped',
    profilingMode: readField(row, 'profilingMode', 'profiling_mode') || 'N/A',
    frequency: readField(row, 'frequency'),
    profilerSummary: readField(row, 'profilerSummary', 'profiler_summary') || 'N/A',
    heartbeatTimestamp: readField(row, 'heartbeatTimestamp', 'heartbeat_timestamp'),
    agentVersion: readField(row, 'agentVersion', 'agent_version'),
    runMode: readField(row, 'runMode', 'run_mode'),
});

const scopeEntityLabel = (scope) => {
    const lookup = {
        service: 'services',
        namespace: 'namespaces',
        host: 'hosts',
        pod: 'pods',
        container: 'containers',
        process: 'processes',
    };
    return lookup[scope] || 'entities';
};

const scopeActiveLabel = (scope) => {
    const lookup = {
        service: 'Active Services',
        namespace: 'Active Namespaces',
        host: 'Active Hosts',
        pod: 'Active Pods',
        container: 'Active Containers',
        process: 'Active Processes',
    };
    return lookup[scope] || 'Active Entities';
};

const rowDisplayName = (row, scope) => {
    if (scope === 'service') return row.service;
    if (scope === 'namespace') return `${row.namespace}`;
    if (scope === 'host') return row.host;
    if (scope === 'pod') return `${row.namespace}/${row.podName}`;
    if (scope === 'container') return `${row.namespace}/${row.podName}/${row.containerName}`;
    return `${row.processName} (${row.pid})`;
};

const ProfilingStatusPage = () => {
    const history = useHistory();
    const location = useLocation();

    const [activeScope, setActiveScope] = useState('service');
    const [rows, setRows] = useState([]);
    const [scopeCounts, setScopeCounts] = useState({});
    const [loading, setLoading] = useState(false);
    const [selectionModel, setSelectionModel] = useState([]);
    const [totalCount, setTotalCount] = useState(0);
    const [page, setPage] = useState(0);
    const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
    const [sortModel, setSortModel] = useState([]);
    // Refs mirror the paging/sort state so the stable fetch callback and the
    // 30s refresh can read current values without being re-created on change.
    const pageRef = useRef(0);
    const pageSizeRef = useRef(DEFAULT_PAGE_SIZE);
    const sortRef = useRef([]);
    // Monotonic request id so a slow response for a stale page/scope is dropped.
    const requestSeq = useRef(0);
    // Timer for the periodic background refresh. It is always cleared and
    // rescheduled by fetchProfilingStatus itself, so it can never fire concurrently
    // with (or duplicate) a manual fetch.
    const autoRefreshTimeoutRef = useRef(null);
    // The query string of the last history.replace we triggered ourselves, so the
    // location-sync effect below can tell that apart from a real external navigation
    // (deep link, browser back/forward) and avoid double-fetching for our own updates.
    const lastSelfUpdatedSearchRef = useRef(null);
    const [filters, setFilters] = useState(EMPTY_FILTERS);
    const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
    const [enablePerfSpect, setEnablePerfSpect] = useState(false);
    const [profilingFrequency, setProfilingFrequency] = useState(DEFAULT_PROFILING_FREQUENCY);
    const [maxProcesses, setMaxProcesses] = useState(DEFAULT_MAX_PROCESSES);
    const [profilingMode, setProfilingMode] = useState('continuous');
    const [duration, setDuration] = useState(DEFAULT_DURATION);
    const [profilerConfigs, setProfilerConfigs] = useState({
        perf: {
            mode: 'enabled_restricted', // 'enabled_restricted', 'enabled_aggressive', 'disabled'
            events: ['cpu-cycles'] // Array of events: 'cpu-cycles', 'instructions', 'cache-misses', etc.
        },
        async_profiler: {
            enabled: true,
            time: 'cpu', // 'cpu', 'itimer', 'wall', 'auto', 'alloc'
            alloc_interval: '2MB' // used only when time === 'alloc'
        },
        pyperf: 'enabled', // 'enabled', 'disabled'
        pyspy: 'enabled_fallback', // 'enabled_fallback', 'enabled', 'disabled'
        rbspy: 'disabled', // 'enabled', 'disabled'
        phpspy: 'disabled', // 'enabled', 'disabled'
        dotnet_trace: 'disabled', // 'enabled', 'disabled'
        nodejs_perf: 'enabled', // 'enabled', 'disabled'
    });
    const [confirmationDialog, setConfirmationDialog] = useState({
        open: false,
        action: null,
        selectedRows: [],
        serviceGroups: {},
    });
    const [dryRunValidation, setDryRunValidation] = useState({
        isValidating: false,
        isValid: false,
        errors: [],
    });
    const [snackbar, setSnackbar] = useState({ open: false, message: '' });

    const columns = useMemo(() => getScopeColumns(activeScope), [activeScope]);

    useEffect(() => {
        try {
            const saved = JSON.parse(localStorage.getItem(CONFIG_STORAGE_KEY));
            if (saved) {
                if (typeof saved.enablePerfSpect === 'boolean') setEnablePerfSpect(saved.enablePerfSpect);
                if (saved.profilingFrequency) setProfilingFrequency(saved.profilingFrequency);
                if (saved.maxProcesses != null) setMaxProcesses(saved.maxProcesses);
                if (saved.profilingMode) setProfilingMode(saved.profilingMode);
                if (saved.duration) setDuration(saved.duration);
                if (saved.profilerConfigs) setProfilerConfigs(saved.profilerConfigs);
            }
        } catch (error) {
            // ignore malformed persisted config
        }
    }, []);

    const handleSaveConfiguration = useCallback(() => {
        const config = {
            enablePerfSpect,
            profilingFrequency,
            maxProcesses,
            profilingMode,
            duration,
            profilerConfigs,
        };
        try {
            localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
            setSnackbar({ open: true, message: 'Configuration saved' });
        } catch (error) {
            setSnackbar({ open: true, message: 'Failed to save configuration' });
        }
    }, [duration, enablePerfSpect, maxProcesses, profilerConfigs, profilingFrequency, profilingMode]);

    const fetchProfilingStatus = useCallback((filterParams, scope, opts = {}) => {
        const pageArg = opts.page ?? pageRef.current;
        const pageSizeArg = opts.pageSize ?? pageSizeRef.current;
        const sortArg = opts.sortModel ?? sortRef.current;
        setLoading(true);
        const params = new URLSearchParams();
        params.append('scope', scope);

        if (filterParams.service) params.append('service_name', filterParams.service);
        if (filterParams.hostname) params.append('hostname', filterParams.hostname);
        if (filterParams.pids) params.append('pids', filterParams.pids);
        if (filterParams.ip) params.append('ip_address', filterParams.ip);
        if (filterParams.namespace) params.append('namespace', filterParams.namespace);
        if (filterParams.podName) params.append('pod_name', filterParams.podName);
        if (filterParams.containerName) params.append('container_name', filterParams.containerName);
        if (filterParams.processName) params.append('process_name', filterParams.processName);
        if (filterParams.commandType) params.append('command_type', filterParams.commandType);
        if (filterParams.status) params.append('profiling_status', filterParams.status);

        params.append('page', pageArg);
        params.append('page_size', pageSizeArg);
        if (sortArg && sortArg.length && SORT_FIELD_MAP[sortArg[0].field]) {
            params.append('sort_by', SORT_FIELD_MAP[sortArg[0].field]);
            params.append('sort_order', sortArg[0].sort || 'asc');
        }

        // Cancel any pending background refresh so it can never fire concurrently with
        // this fetch (manual or auto); the next refresh is (re)scheduled once this settles.
        if (autoRefreshTimeoutRef.current) {
            clearTimeout(autoRefreshTimeoutRef.current);
        }

        const seq = ++requestSeq.current;
        fetch(`${DATA_URLS.GET_PROFILING_WORKLOAD_STATUS}?${params.toString()}`)
            .then((res) => res.json())
            .then((data) => {
                if (seq !== requestSeq.current) return; // a newer request superseded this one
                const normalizedRows = (data.rows || []).map((row) => formatRowForScope(row, scope));
                setRows(normalizedRows);
                setScopeCounts(data.tabCounts || data.tab_counts || {});
                setTotalCount(data.totalCount || data.total_count || normalizedRows.length);
                setLoading(false);
            })
            .catch(() => {
                if (seq === requestSeq.current) setLoading(false);
            })
            .finally(() => {
                // Only the request that is still current gets to schedule the next
                // background refresh, using the filters/scope it just displayed.
                if (seq === requestSeq.current) {
                    autoRefreshTimeoutRef.current = setTimeout(() => {
                        fetchProfilingStatus(filterParams, scope);
                    }, AUTO_REFRESH_INTERVAL_MS);
                }
            });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);


    const updateURL = useCallback((scope, nextFilters) => {
        const searchParams = { scope };
        Object.keys(nextFilters).forEach((key) => {
            if (nextFilters[key]) {
                searchParams[key] = nextFilters[key];
            }
        });
        const search = queryString.stringify(searchParams);
        // Remember that we caused this URL change so the location-sync effect below
        // (deep links / browser back-forward) doesn't also re-fetch for it.
        lastSelfUpdatedSearchRef.current = search;
        history.replace({ pathname: '/profiling', search });
    }, [history]);

    const applyFilters = useCallback(() => {
        setAppliedFilters(filters);
        setSelectionModel([]);
        pageRef.current = 0;
        setPage(0);
        fetchProfilingStatus(filters, activeScope, { page: 0 });
        updateURL(activeScope, filters);
    }, [activeScope, fetchProfilingStatus, filters, updateURL]);

    const clearAllFilters = useCallback(() => {
        setFilters(EMPTY_FILTERS);
        setAppliedFilters(EMPTY_FILTERS);
        setSelectionModel([]);
        pageRef.current = 0;
        setPage(0);
        fetchProfilingStatus(EMPTY_FILTERS, activeScope, { page: 0 });
        updateURL(activeScope, EMPTY_FILTERS);
    }, [activeScope, fetchProfilingStatus, updateURL]);

    const updateFilter = useCallback((field, value) => {
        setFilters((prev) => ({ ...prev, [field]: value }));
    }, []);

    useEffect(() => {
        // Skip URL changes we triggered ourselves (applyFilters/clearAllFilters/
        // handleScopeChange already fetched with the new state); only react here to
        // real external navigation, such as a deep link or the browser back/forward
        // buttons, so we don't fire a second, duplicate request for our own updates.
        const currentSearch = location.search.replace(/^\?/, '');
        if (lastSelfUpdatedSearchRef.current !== null && currentSearch === lastSelfUpdatedSearchRef.current) {
            lastSelfUpdatedSearchRef.current = null;
            return;
        }

        const searchParams = queryString.parse(location.search);
        const scope = searchParams.scope || 'service';
        const urlFilters = {
            service: searchParams.service || '',
            hostname: searchParams.hostname || '',
            pids: searchParams.pids || '',
            ip: searchParams.ip || '',
            namespace: searchParams.namespace || '',
            podName: searchParams.podName || '',
            containerName: searchParams.containerName || '',
            processName: searchParams.processName || '',
            commandType: searchParams.commandType || '',
            status: searchParams.status || '',
        };
        setActiveScope(scope);
        setFilters(urlFilters);
        setAppliedFilters(urlFilters);
        pageRef.current = 0;
        setPage(0);
        sortRef.current = [];
        setSortModel([]);
        fetchProfilingStatus(urlFilters, scope, { page: 0, sortModel: [] });
    }, [fetchProfilingStatus, location.search]);

    useEffect(() => {
        // fetchProfilingStatus reschedules itself after every call (see above); this
        // only needs to cancel a pending timer if the page unmounts mid-cycle.
        return () => {
            if (autoRefreshTimeoutRef.current) {
                clearTimeout(autoRefreshTimeoutRef.current);
            }
        };
    }, []);

    const handleScopeChange = (_, nextScope) => {
        setActiveScope(nextScope);
        setSelectionModel([]);
        pageRef.current = 0;
        setPage(0);
        sortRef.current = [];
        setSortModel([]);
        fetchProfilingStatus(appliedFilters, nextScope, { page: 0, sortModel: [] });
        updateURL(nextScope, appliedFilters);
    };

    const handlePageChange = useCallback((newPage) => {
        pageRef.current = newPage;
        setPage(newPage);
        setSelectionModel([]); // selection is per-page (Gmail-style)
        fetchProfilingStatus(appliedFilters, activeScope, { page: newPage });
    }, [activeScope, appliedFilters, fetchProfilingStatus]);

    const handlePageSizeChange = useCallback((newSize) => {
        pageSizeRef.current = newSize;
        setPageSize(newSize);
        pageRef.current = 0;
        setPage(0);
        setSelectionModel([]);
        fetchProfilingStatus(appliedFilters, activeScope, { page: 0, pageSize: newSize });
    }, [activeScope, appliedFilters, fetchProfilingStatus]);

    const handleSortModelChange = useCallback((model) => {
        sortRef.current = model;
        setSortModel(model);
        pageRef.current = 0;
        setPage(0);
        fetchProfilingStatus(appliedFilters, activeScope, { page: 0, sortModel: model });
    }, [activeScope, appliedFilters, fetchProfilingStatus]);

    const buildRequests = useCallback((action, selectedRows) => buildProfilingRequests(action, selectedRows, {
        scope: activeScope,
        profilingMode,
        duration,
        profilingFrequency,
        enablePerfSpect,
        profilerConfigs,
        maxProcesses,
    }), [activeScope, duration, enablePerfSpect, maxProcesses, profilerConfigs, profilingFrequency, profilingMode]);

    const executeDryRun = useCallback((action, selectedRows) => {
        const { requests } = buildRequests(action, selectedRows);
        setDryRunValidation({ isValidating: true, isValid: false, errors: [] });

        fetch(DATA_URLS.POST_PROFILING_REQUEST_BULK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requests, dry_run: true }),
        })
            .then((res) => {
                if (!res.ok) {
                    return res.json().then((errData) => {
                        if (errData.detail && Array.isArray(errData.detail)) {
                            throw new Error(errData.detail.map((err) => err.msg || JSON.stringify(err)).join('; '));
                        }
                        throw new Error(errData.detail || `Validation failed with status ${res.status}`);
                    });
                }
                return res.json();
            })
            .then((bulkResponse) => {
                const errors = (bulkResponse.results || [])
                    .filter((result) => !result.success)
                    .map((result) => `${result.service_name}: ${result.error}`);
                setDryRunValidation({
                    isValidating: false,
                    isValid: (bulkResponse.failed_count || 0) === 0,
                    errors,
                });
            })
            .catch((error) => {
                setDryRunValidation({
                    isValidating: false,
                    isValid: false,
                    errors: [error.message],
                });
            });
    }, [buildRequests]);

    const handleBulkAction = (action) => {
        const selectedRows = rows.filter((row) => selectionModel.includes(row.id));
        const { grouped } = buildRequests(action, selectedRows);
        setConfirmationDialog({
            open: true,
            action,
            selectedRows,
            serviceGroups: grouped,
        });
        executeDryRun(action, selectedRows);
    };

    const executeProfilingAction = () => {
        const { action, selectedRows } = confirmationDialog;
        const { requests } = buildRequests(action, selectedRows);

        setConfirmationDialog({ open: false, action: null, selectedRows: [], serviceGroups: {} });
        setDryRunValidation({ isValidating: false, isValid: false, errors: [] });

        fetch(DATA_URLS.POST_PROFILING_REQUEST_BULK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requests, dry_run: false }),
        }).then(() => {
            fetchProfilingStatus(appliedFilters, activeScope);
            setSelectionModel([]);
            setEnablePerfSpect(false);
        });
    };

    const handleDialogClose = () => {
        setConfirmationDialog({ open: false, action: null, selectedRows: [], serviceGroups: {} });
        setDryRunValidation({ isValidating: false, isValid: false, errors: [] });
    };

    return (
        <Box sx={{ backgroundColor: 'white.main', height: '100%' }}>
            <Box
                sx={{
                    px: 4,
                    pt: 3,
                    pb: 1,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 2,
                }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Icon name={ICONS_NAMES.Crosshairs} size={28} color="#583FFD" />
                    <Box>
                        <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
                            Adhoc Profile Configuration
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Select workloads and configure profiling parameters
                        </Typography>
                    </Box>
                </Box>
                <Box sx={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {scopeActiveLabel(activeScope)}
                    </Typography>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#16a34a' }}>
                        {(scopeCounts[activeScope] ?? totalCount ?? 0).toLocaleString()}
                    </Typography>
                </Box>
            </Box>

            <ProfilingHeader
                filters={filters}
                updateFilter={updateFilter}
                isLoading={loading}
                onApplyFilters={applyFilters}
                onClearFilters={clearAllFilters}
            />

            <Box sx={{ px: 4, pt: 2 }}>
                <Tabs value={activeScope} onChange={handleScopeChange} variant="scrollable" scrollButtons="auto">
                    {SCOPES.map((scope) => (
                        <Tab
                            key={scope.id}
                            value={scope.id}
                            label={`${scope.label} ${scopeCounts[scope.id] ? scopeCounts[scope.id] : ''}`.trim()}
                        />
                    ))}
                </Tabs>
            </Box>

            <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                <Box sx={{ px: 4, pt: 3, pb: 1, '& .MuiDataGrid-root': { border: 'none' } }}>
                    <MuiTable
                        columns={columns}
                        data={rows}
                        isLoading={loading}
                        pageSize={pageSize}
                        rowHeight={50}
                        paginationMode="server"
                        rowCount={totalCount}
                        page={page}
                        onPageChange={handlePageChange}
                        onPageSizeChange={handlePageSizeChange}
                        sortingMode="server"
                        sortModel={sortModel}
                        onSortModelChange={handleSortModelChange}
                        checkboxSelection
                        onSelectionModelChange={setSelectionModel}
                        selectionModel={selectionModel}
                    />
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                        Showing {rows.length} of {totalCount} {scopeEntityLabel(activeScope)}
                        {selectionModel.length ? ` \u00b7 ${selectionModel.length} selected on this page` : ''}
                    </Typography>
                </Box>

                <ProfilingTopPanel
                    selectionModel={selectionModel}
                    handleBulkAction={handleBulkAction}
                    fetchProfilingStatus={(scopeFilters) => fetchProfilingStatus(scopeFilters, activeScope)}
                    filters={appliedFilters}
                    loading={loading}
                    enablePerfSpect={enablePerfSpect}
                    onPerfSpectChange={setEnablePerfSpect}
                    profilingFrequency={profilingFrequency}
                    onProfilingFrequencyChange={setProfilingFrequency}
                    maxProcesses={maxProcesses}
                    onMaxProcessesChange={setMaxProcesses}
                    profilingMode={profilingMode}
                    onProfilingModeChange={setProfilingMode}
                    duration={duration}
                    onDurationChange={setDuration}
                    profilerConfigs={profilerConfigs}
                    onProfilerConfigsChange={setProfilerConfigs}
                    onSaveConfiguration={handleSaveConfiguration}
                />
            </Box>

            <Dialog open={confirmationDialog.open} onClose={handleDialogClose} maxWidth="md" fullWidth>
                <DialogTitle>
                    <Typography variant="h6">
                        Confirm {confirmationDialog.action === 'start' ? 'Start' : 'Stop'} Profiling
                    </Typography>
                </DialogTitle>
                <DialogContent>
                    {dryRunValidation.isValidating && (
                        <Box sx={{ mb: 2, p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
                            <Typography variant="body2" color="text.secondary">
                                Validating request...
                            </Typography>
                        </Box>
                    )}
                    {!dryRunValidation.isValidating && dryRunValidation.isValid && (
                        <Box sx={{ mb: 2, p: 2, backgroundColor: '#e8f5e9', borderRadius: 1 }}>
                            <Typography variant="body2" color="success.dark">
                                ✓ Validation successful
                            </Typography>
                        </Box>
                    )}
                    {!dryRunValidation.isValidating && !dryRunValidation.isValid && dryRunValidation.errors.length > 0 && (
                        <Box sx={{ mb: 2, p: 2, backgroundColor: '#ffebee', borderRadius: 1 }}>
                            <Typography variant="body2" color="error.dark" sx={{ fontWeight: 600, mb: 1 }}>
                                ✗ Validation failed
                            </Typography>
                            {dryRunValidation.errors.map((error, idx) => (
                                <Typography key={idx} variant="body2" color="error.dark" sx={{ mt: 0.5, whiteSpace: 'pre-line' }}>
                                    • {error}
                                </Typography>
                            ))}
                        </Box>
                    )}

                    <Typography variant="body1" sx={{ mb: 2 }}>
                        Are you sure you want to <strong>{confirmationDialog.action}</strong> profiling for the selected {scopeEntityLabel(activeScope)}?
                    </Typography>

                    <Box sx={{ mb: 3 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                            Selected {scopeEntityLabel(activeScope)} ({confirmationDialog.selectedRows.length}):
                        </Typography>
                        {Object.entries(confirmationDialog.serviceGroups).map(([serviceName, serviceRows]) => (
                            <Box key={serviceName} sx={{ mb: 2 }}>
                                <Typography variant="body2" sx={{ fontWeight: 500, mb: 0.5 }}>
                                    {serviceName}:
                                </Typography>
                                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                    {serviceRows.map((row) => (
                                        <Chip
                                            key={row.id}
                                            label={rowDisplayName(row, activeScope)}
                                            size="small"
                                            variant="outlined"
                                            sx={{
                                                borderColor: dryRunValidation.isValid ? '#2e7d32' : '#d32f2f',
                                                color: dryRunValidation.isValid ? '#2e7d32' : '#d32f2f',
                                            }}
                                        />
                                    ))}
                                </Box>
                            </Box>
                        ))}
                    </Box>

                    {confirmationDialog.action === 'start' && (
                        <>
                            <Divider sx={{ my: 2 }} />
                            <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
                                Profiling Configuration:
                            </Typography>
                            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                                <Box>
                                    <Typography variant="body2" sx={{ fontWeight: 500, mb: 1 }}>
                                        Basic Settings:
                                    </Typography>
                                    <Typography variant="body2">• Frequency: {profilingFrequency} Hz</Typography>
                                    <Typography variant="body2">• Max Processes: {maxProcesses}</Typography>
                                    <Typography variant="body2">• PerfSpect HW Metrics: {enablePerfSpect ? 'Enabled' : 'Disabled'}</Typography>
                                    <Typography variant="body2">• Profiling Mode: {profilingMode === 'adhoc' ? 'Ad Hoc' : 'Continuous'}</Typography>
                                    <Typography variant="body2">• Duration: {profilingMode === 'continuous' ? 60 : duration} seconds</Typography>
                                    <Typography variant="body2">• Mode: CPU profiling</Typography>
                                </Box>
                                <Box>
                                    <Typography variant="body2" sx={{ fontWeight: 500, mb: 1 }}>
                                        Profiler Settings:
                                    </Typography>
                                    <Typography variant="body2">• Perf (C/C++/Go): {
                                        profilerConfigs.perf?.mode === 'enabled_restricted' ? 'Enabled (Restricted)' :
                                        profilerConfigs.perf?.mode === 'enabled_aggressive' ? 'Enabled (Aggressive)' : 'Disabled'
                                    }</Typography>
                                    <Typography variant="body2">• Java Async Profiler: {
                                        profilerConfigs.async_profiler?.enabled
                                            ? `Enabled (${
                                                profilerConfigs.async_profiler.time === 'wall' ? 'Wall Time' :
                                                profilerConfigs.async_profiler.time === 'itimer' ? 'ITimer' :
                                                profilerConfigs.async_profiler.time === 'auto' ? 'Auto' :
                                                profilerConfigs.async_profiler.time === 'alloc' ? `Allocation (${profilerConfigs.async_profiler.alloc_interval || '2MB'})` :
                                                'CPU Time'
                                            })`
                                            : 'Disabled'
                                    }</Typography>
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
                    <Button onClick={handleDialogClose}>Cancel</Button>
                    <Button
                        onClick={executeProfilingAction}
                        color={confirmationDialog.action === 'start' ? 'success' : 'error'}
                        variant="contained"
                        disabled={dryRunValidation.isValidating || !dryRunValidation.isValid}
                    >
                        {confirmationDialog.action === 'start' ? 'Start Profiling' : 'Stop Profiling'}
                    </Button>
                </DialogActions>
            </Dialog>

            <Snackbar
                open={snackbar.open}
                autoHideDuration={3000}
                onClose={() => setSnackbar({ open: false, message: '' })}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
            >
                <Alert
                    onClose={() => setSnackbar({ open: false, message: '' })}
                    severity="success"
                    variant="filled"
                    sx={{ width: '100%' }}
                >
                    {snackbar.message}
                </Alert>
            </Snackbar>
        </Box>
    );
};

export default ProfilingStatusPage;
