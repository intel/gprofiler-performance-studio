/*
 * Acceptance / spec tests for the profiling request builder.
 *
 * These encode the executable specification for how the Profiling Status page
 * turns selected inventory rows into POST /api/metrics/profile_request payloads.
 * They run with Node's built-in test runner (no extra dependencies):
 *
 *     node --test src/gprofiler/frontend/src/components/console/profilingRequestBuilder.test.mjs
 *
 * The central invariant (which the original host/service stop bug violated):
 *   A host- or service-level STOP must never carry a PID, or the backend
 *   ProfilingRequest validator rejects it with
 *   'No PIDs should be provided when request_type is "stop" and stop_level is "host"'.
 */

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
    HOST_LEVEL_SCOPES,
    buildProfilingRequests,
    buildTargetEntity,
    groupRowsByService,
    resolveStopLevel,
} from './profilingRequestBuilder.mjs';

const baseConfig = {
    scope: 'host',
    profilingMode: 'adhoc',
    duration: 120,
    profilingFrequency: 11,
    enablePerfSpect: false,
    profilerConfigs: {},
    maxProcesses: 10,
};

const makeRow = (overrides = {}) => ({
    id: 'row-1',
    service: 'svc-a',
    namespace: 'ns-a',
    host: 'host-a',
    ip: '10.0.0.1',
    podName: 'pod-a',
    containerName: 'cont-a',
    workloadName: 'wl-a',
    workloadKind: 'Deployment',
    processName: 'python',
    pid: 4242,
    ...overrides,
});

// Every target entity produced for a request, flattened.
const allEntities = (requests) => requests.flatMap((r) => r.target_entities);
// True when any produced entity carries a PID (what the backend forbids for host stops).
const anyEntityHasPid = (requests) => allEntities(requests).some((e) => e.pid !== undefined);

describe('buildTargetEntity', () => {
    it('omits process-level identifiers (pid/process_name) for coarse scopes', () => {
        for (const scope of ['service', 'host', 'namespace', 'workload', 'pod', 'container']) {
            const entity = buildTargetEntity(makeRow(), scope);
            assert.equal(entity.pid, undefined, `pid must be undefined for scope=${scope}`);
            assert.equal(
                entity.process_name,
                undefined,
                `process_name must be undefined for scope=${scope}`
            );
        }
    });

    it('includes pid and process_name for the process scope', () => {
        const entity = buildTargetEntity(makeRow({ pid: 4242, processName: 'python' }), 'process');
        assert.equal(entity.pid, 4242);
        assert.equal(entity.process_name, 'python');
    });

    it('preserves a legitimate PID of 0 (not dropped as falsy)', () => {
        const entity = buildTargetEntity(makeRow({ pid: 0 }), 'process');
        assert.equal(entity.pid, 0);
    });

    it('treats a missing PID as undefined for the process scope', () => {
        const entity = buildTargetEntity(makeRow({ pid: null }), 'process');
        assert.equal(entity.pid, undefined);
    });

    it('always carries the identifying fields needed for host-scope resolution', () => {
        const entity = buildTargetEntity(makeRow(), 'host');
        assert.equal(entity.service_name, 'svc-a');
        assert.equal(entity.hostname, 'host-a');
    });
});

describe('resolveStopLevel', () => {
    it('is undefined for start requests regardless of scope', () => {
        for (const scope of ['service', 'host', 'process']) {
            assert.equal(resolveStopLevel('start', scope), undefined);
        }
    });

    it('is "host" for coarse (service/host) stop scopes', () => {
        for (const scope of HOST_LEVEL_SCOPES) {
            assert.equal(resolveStopLevel('stop', scope), 'host');
        }
    });

    it('is "process" for finer stop scopes', () => {
        for (const scope of ['namespace', 'workload', 'pod', 'container', 'process']) {
            assert.equal(resolveStopLevel('stop', scope), 'process');
        }
    });
});

describe('groupRowsByService', () => {
    it('groups rows by service preserving order', () => {
        const grouped = groupRowsByService([
            makeRow({ id: '1', service: 'svc-a' }),
            makeRow({ id: '2', service: 'svc-b' }),
            makeRow({ id: '3', service: 'svc-a' }),
        ]);
        assert.deepEqual(Object.keys(grouped), ['svc-a', 'svc-b']);
        assert.equal(grouped['svc-a'].length, 2);
        assert.equal(grouped['svc-b'].length, 1);
    });
});

describe('buildProfilingRequests — host-level stop (the regression)', () => {
    it('produces a host-level stop with no PIDs anywhere', () => {
        const { requests } = buildProfilingRequests('stop', [makeRow()], {
            ...baseConfig,
            scope: 'host',
        });

        assert.equal(requests.length, 1);
        const [req] = requests;
        assert.equal(req.request_type, 'stop');
        assert.equal(req.stop_level, 'host');
        // target_hosts maps host -> null (whole-host target, no PIDs).
        assert.deepEqual(req.target_hosts, { 'host-a': null });
        // No target entity may carry a PID.
        assert.equal(anyEntityHasPid(requests), false);
    });

    it('produces a service-level stop with no PIDs and no target_hosts map', () => {
        const { requests } = buildProfilingRequests('stop', [makeRow()], {
            ...baseConfig,
            scope: 'service',
        });

        const [req] = requests;
        assert.equal(req.stop_level, 'host');
        assert.equal(req.target_scope, 'service');
        assert.equal(req.target_hosts, undefined);
        assert.equal(anyEntityHasPid(requests), false);
    });
});

describe('buildProfilingRequests — process-level stop', () => {
    it('is a process-level stop that includes the PID', () => {
        const { requests } = buildProfilingRequests('stop', [makeRow({ pid: 4242 })], {
            ...baseConfig,
            scope: 'process',
        });

        const [req] = requests;
        assert.equal(req.stop_level, 'process');
        assert.equal(req.target_hosts, undefined);
        assert.equal(req.target_entities[0].pid, 4242);
        assert.equal(anyEntityHasPid(requests), true);
    });
});

describe('buildProfilingRequests — start requests', () => {
    it('never sets stop_level for a start', () => {
        for (const scope of ['service', 'host', 'process']) {
            const { requests } = buildProfilingRequests('start', [makeRow()], {
                ...baseConfig,
                scope,
            });
            assert.equal(requests[0].stop_level, undefined);
        }
    });

    it('forces continuous mode to a 60s duration', () => {
        const { requests } = buildProfilingRequests('start', [makeRow()], {
            ...baseConfig,
            profilingMode: 'continuous',
            duration: 999,
        });
        assert.equal(requests[0].continuous, true);
        assert.equal(requests[0].duration, 60);
    });

    it('uses the configured duration for ad-hoc mode', () => {
        const { requests } = buildProfilingRequests('start', [makeRow()], {
            ...baseConfig,
            profilingMode: 'adhoc',
            duration: 120,
        });
        assert.equal(requests[0].continuous, false);
        assert.equal(requests[0].duration, 120);
    });
});

describe('buildProfilingRequests — multi-service', () => {
    it('emits one request per service', () => {
        const { requests } = buildProfilingRequests(
            'stop',
            [
                makeRow({ id: '1', service: 'svc-a', host: 'h1' }),
                makeRow({ id: '2', service: 'svc-b', host: 'h2' }),
            ],
            { ...baseConfig, scope: 'host' }
        );

        assert.equal(requests.length, 2);
        assert.deepEqual(
            requests.map((r) => r.service_name).sort(),
            ['svc-a', 'svc-b']
        );
        assert.equal(anyEntityHasPid(requests), false);
    });
});

/*
 * The client half of the WORKLOAD_LEVEL_PROFILING_SPEC.md resolution contract.
 * The backend does the actual host/PID resolution, but the request the UI emits
 * must carry exactly the selectors each scope needs — and nothing that would be
 * rejected. These map to AT-S5 (host start), AT-S6 (service fan-out), and AT-S7
 * (workload scopes resolve to PIDs).
 */
describe('buildProfilingRequests — scope matrix (start)', () => {
    // AT-S5: a host-scope start targets the concrete host via target_hosts.
    it('host scope emits a target_hosts map and no PIDs', () => {
        const { requests } = buildProfilingRequests('start', [makeRow({ host: 'host-a' })], {
            ...baseConfig,
            scope: 'host',
        });
        assert.deepEqual(requests[0].target_hosts, { 'host-a': null });
        assert.equal(anyEntityHasPid(requests), false);
    });

    // AT-S6: a service-scope start carries no target_hosts (backend fans out to
    // every current host of the service) but still names the service.
    it('service scope carries the service selector and no target_hosts', () => {
        const { requests } = buildProfilingRequests(
            'start',
            [makeRow({ service: 'svc-a', host: 'h1' }), makeRow({ id: '2', service: 'svc-a', host: 'h2' })],
            { ...baseConfig, scope: 'service' }
        );
        assert.equal(requests.length, 1);
        assert.equal(requests[0].service_name, 'svc-a');
        assert.equal(requests[0].target_hosts, undefined);
        assert.equal(requests[0].target_scope, 'service');
        assert.equal(anyEntityHasPid(requests), false);
    });

    // AT-S7: namespace/workload/pod/container select via entity metadata (no PID
    // on the client — the backend resolves these to PIDs), while `process`
    // carries the concrete PID.
    it('sub-host scopes attach the right selectors; only process carries a PID', () => {
        const cases = {
            namespace: (e) => assert.equal(e.namespace, 'ns-a'),
            workload: (e) => assert.equal(e.workload_name, 'wl-a'),
            pod: (e) => assert.equal(e.pod_name, 'pod-a'),
            container: (e) => assert.equal(e.container_name, 'cont-a'),
        };
        for (const [scope, assertSelector] of Object.entries(cases)) {
            const { requests } = buildProfilingRequests('start', [makeRow()], { ...baseConfig, scope });
            const [entity] = requests[0].target_entities;
            assertSelector(entity);
            assert.equal(entity.pid, undefined, `pid must be undefined for scope=${scope}`);
        }

        const { requests: procReqs } = buildProfilingRequests('start', [makeRow({ pid: 4242 })], {
            ...baseConfig,
            scope: 'process',
        });
        assert.equal(procReqs[0].target_entities[0].pid, 4242);
    });

    it('threads perf/perfspect config through additional_args unchanged', () => {
        const profilerConfigs = { perf: { mode: 'enabled_restricted', events: ['cycles'] } };
        const { requests } = buildProfilingRequests('start', [makeRow()], {
            ...baseConfig,
            scope: 'service',
            enablePerfSpect: true,
            profilerConfigs,
            maxProcesses: 25,
        });
        assert.deepEqual(requests[0].additional_args, {
            enable_perfspect: true,
            profiler_configs: profilerConfigs,
            max_processes: 25,
        });
    });
});
