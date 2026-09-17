# Workload Status (`GET /profiling/workload_status`) — performance follow-ups

## Context

At ~34K active hosts / ~684K total `HostHeartbeats` rows (PROD, Sep 2026) the endpoint
timed out (>30s). Root causes, from prod `EXPLAIN (ANALYZE)`:

1. **Bad plan from `ORDER BY/GROUP BY service_name`** — the planner did a full scan of
   `idx_hostheartbeats_service_name` (cost ~126K) over all 684K rows, applying the
   `heartbeat_timestamp > now()-2min` freshness filter as a per-row heap filter, to avoid a
   sort. Random I/O over the whole table → timeout.
2. **Table bloat / no retention** — only ~34K of 684K hosts are active; ~650K are stale
   decommissioned hosts that are never cleaned up. Every request scans all of them.
3. **`COUNT(*) OVER ()`** (`total_groups`) prevents `LIMIT` from short-circuiting.

## Shipped in this change (a)

- Restrict to the active fleet **first**, in a `fresh_hosts AS MATERIALIZED (…)` CTE, so
  grouping/sorting can no longer drive the full-index scan.
- Dropped the redundant `latest_commands` window (`ProfilingCommands` is already
  `UNIQUE (hostname, service_name)`).

Measured on PROD (read-only `EXPLAIN ANALYZE`), `scope=host`, page 0:

| Query | Before | After (a) |
| --- | --- | --- |
| grouped rows | **timeout (>30s)** | **~1.4s** |

Uniform across all scopes, no schema change, no semantic change (all filters still applied
in `filtered`).

---

## Follow-up (b) — entity-first pagination  ✅ shipped (as a hybrid)

**Original idea:** page the *driving entity* first, then aggregate only the page via
`LATERAL` joins for just those ≤`page_size` entities; get `total_count` from a single
`COUNT(*)` over the driving set and drop `COUNT(*) OVER ()`.

**What changed since this was written:** the workload agent rolled out, so
`HeartbeatContainers` (~316K) and `HeartbeatProcesses` (~1.08M) are now populated and the
flatten is ~1.08M rows (was ~34K when only hosts existed). Pure entity-first is a big win
for scopes with *many small* entities but *regresses* for scopes with *few large* entities
(a page of 50 services still covers most of the fleet, and each per-entity `LATERAL`
re-scans a whole service). So (b) shipped as a **hybrid**, chosen per scope:

- **Entity-first** (`host`, `container`, `process` — many small entities): page the key set,
  then hydrate only that page via a `LATERAL` that reads `HostHeartbeats` **directly**
  (indexed on `service_name`/`hostname`). Only host-level keys are correlated with `=`;
  finer keys are NULL-safe residual filters (never pushed onto child tables, or the planner
  drives from a global `idx_hb_containers_namespace` scan and explodes on `default`/
  `kube-system`).
- **Single-pass** (`namespace`, `pod` — few/large, PID-aware): one `GROUP BY` over the
  flatten, paginated (the guard `namespace/pod_name IS NOT NULL` prunes the fan-out).
- **Two-grain single-pass** (`service`): counts + latest metadata at the container grain
  (~316K rows), `process_count` via `COUNT(*) FROM (SELECT DISTINCT …) GROUP BY`, and
  `any_active` at the **host** grain — provably identical to the PID-aware value for service
  scope (verified 0/460 services differ on prod). Falls back to plain single-pass under a
  process-tier filter.

**Measured (prod, page 0):** grouped `host` ~10s → **~0.6s**; `container` ~2.0s;
`process` ~3.7s; `namespace` ~3.5s; `pod` ~4.1s; `service` ~16s → **~6.4s**.

**Gate:** query-only, but higher correctness risk than (a) (filter push-down level,
NULL-safe intermediate keys, the service `any_active` equivalence). Validated read-only on
prod against authoritative counts; still gate on the `AT-S1..S17` workload-acceptance tests.

## Follow-up (c) — targeted `tab_counts`  ✅ shipped

The single 7×`COUNT(DISTINCT …)` pass timed out once the child tables filled. Replaced with
targeted per-tier counts sharing the `fresh_hosts` CTE:

- `service` / `host` / `active_hosts` → from `fresh_hosts` only.
- `namespace` / `pod` / `container` → `HeartbeatContainers ⋈ fresh_hosts`.
- `process` → 3-way join, distinct on the integer `(host_id, pid)`.

Each count uses `COUNT(*) FROM (SELECT DISTINCT …)` (hash-distinct) instead of
`COUNT(DISTINCT tuple)` (sort-per-aggregate) — the process count alone went
**13.2s → 0.84s**. All filters still apply at every tier.

**Measured (prod):** **timeout → ~4s** (tier A ~0.4s + B ~1.1s + C ~0.8s). Short-TTL caching
was *not* added and remains an option if the tabs need to feel instant.

## Follow-up — retention cleanup (root cause)  ⏳ outstanding

The unbounded growth of `HostHeartbeats` / `HeartbeatContainers` / `HeartbeatProcesses` is
the structural driver: ~95% of `HostHeartbeats` rows are stale, and the child tables now
carry ~1.08M live-plus-stale rows. A periodic cleanup that deletes hosts whose
`heartbeat_timestamp` is older than a retention threshold (child tables cascade via FK)
would shrink the base tables ~20×.

- The parallel seq scan to extract the fresh set drops from ~100ms to ~10ms.
- Every scan, index, and autovacuum on these tables gets ~20× cheaper.
- It is the single change that would bring the heavier scopes (`service`, `pod`) back to
  sub-second and keep them there as the fleet grows.
- Natural home: the `deploy/periodic_tasks` container (cron), matching the existing
  aggregation/logrotate jobs.

## Status / suggested order

1. **(a)** — shipped (killed the original host-scan timeout; PR #95).
2. **(c) tiered `tab_counts`** — shipped (timeout → ~4s).
3. **(b) hybrid entity-first / single-pass / two-grain** — shipped (default `host` view
   ~10s → ~0.6s; all scopes under the timeout).
4. **Retention job** — outstanding; the biggest remaining structural win, benefits every
   scope and is what would bring `service` (~6.4s) and `pod` (~4.1s) back to sub-second.

