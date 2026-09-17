# Webapp DB Concurrency Tuning

Environment variables that control how much database work the webapp
(`gprofiler_frontend` container) can do in parallel, and how to set them in
production.

## Background: why this matters

The webapp runs under **gunicorn** with **`uvicorn.workers.UvicornWorker`**
(async workers). The API route handlers are synchronous `def` functions, so
Starlette runs each request in a **per-worker threadpool** (anyio default: 40
threads).

Database access goes through `PostgresDB`, which by default keeps **one shared
psycopg2 connection per worker process**, guarded by a process-wide lock. Every
query — read or write — is serialized through that single connection:

```
worker process
  ├─ ~40 request threads accepted concurrently
  └─ 1 DB connection + lock  ← all threads queue here
```

This is fine at low load, but when an expensive request (e.g.
`POST /api/metrics/heartbeat`) holds the connection, **every other endpoint in
that worker stalls behind it**. Under production heartbeat volume this starves
reads and all endpoints start hitting the 15 s load-balancer timeout — even
ones whose own query takes milliseconds.

The knobs below let you add real DB concurrency without a code change.

## The knobs

| Environment variable | Where read | Default | Effect |
| --- | --- | --- | --- |
| `GUNICORN_PROCESS_COUNT` | `src/gprofiler/run.sh` | `nproc` | Number of gunicorn worker **processes** per replica. Each worker is a separate process with its own DB connection(s). |
| `GPROFILER_POSTGRES_CONN_PER_THREAD` | `src/gprofiler-dev/gprofiler_dev/config.py` | `FALSE` | When `TRUE`, each worker **thread** gets its own DB connection instead of sharing one. This removes the per-worker serialization. |
| `GPROFILER_WEBAPP_THREAD_POOL_SIZE` | `src/gprofiler/backend/config.py` | `0` (keep anyio default of 40) | Per-worker threadpool size for sync route handlers. With `CONN_PER_THREAD=TRUE` this also caps the number of DB connections each worker can open. |

### `GPROFILER_POSTGRES_CONN_PER_THREAD` — the primary fix

This is the highest-leverage setting. With it `FALSE` (the default), a worker
can only run **one** DB operation at a time regardless of how many requests it
accepts. Setting it to `TRUE` gives each threadpool thread its own connection,
so a single worker can run up to `threadpool_size` queries in parallel.

Set this to `TRUE` first — it directly removes the cross-endpoint starvation.

### `GUNICORN_PROCESS_COUNT` — raw process concurrency

Each worker is a separate process (and, with `CONN_PER_THREAD=FALSE`, exactly
one DB connection). Increasing workers multiplies DB concurrency **across**
processes. Because the workers are I/O-bound on the database, it is fine to run
more workers than CPU cores. Useful as a throughput multiplier on top of
`CONN_PER_THREAD=TRUE`, or as the only lever if you keep `CONN_PER_THREAD=FALSE`.

### `GPROFILER_WEBAPP_THREAD_POOL_SIZE` — bound / widen per-worker concurrency

Controls how many sync requests a worker runs at once. Leave at `0` to keep the
framework default (40). Raise it to allow more in-flight requests per worker;
lower it to **bound the number of DB connections** when
`CONN_PER_THREAD=TRUE` (see the connection math below).

## Connection math

Total DB connections opened by the webapp is approximately:

```
connections ≈ replicas × GUNICORN_PROCESS_COUNT × threads_per_worker
```

where `threads_per_worker` is:

- `1` when `GPROFILER_POSTGRES_CONN_PER_THREAD=FALSE` (shared connection), or
- `GPROFILER_WEBAPP_THREAD_POOL_SIZE` (or 40 if unset) when `TRUE`.

Stay under the database's `max_connections`. On the current Aurora cluster
`max_connections = 5000` with only ~70 in use, so there is large headroom.

**Examples (per the current prod cluster, `nproc = 8`):**

| Config | Conns/replica | 6 replicas |
| --- | --- | --- |
| Current: `CONN_PER_THREAD=FALSE`, 8 workers | 8 | 48 |
| `CONN_PER_THREAD=TRUE`, 8 workers, pool 40 (default) | 320 | 1920 |
| `CONN_PER_THREAD=TRUE`, 8 workers, pool 20 | 160 | 960 |
| `CONN_PER_THREAD=FALSE`, 24 workers | 24 | 144 |

## Sizing for load (Little's Law)

The number of DB operations in flight at once is `L = λ × W`, where `λ` is the
request rate and `W` is how long each request holds a connection. Your total
provisioned concurrency (`replicas × workers × threads_per_worker`) must exceed
`L`, with headroom for bursts.

The dominant driver here is the agent heartbeat: **30k hosts × 1 per 30 s ≈
1000 heartbeat QPS**. Each heartbeat is write-heavy — `upsert_host_heartbeat`
(host upsert + container/process diff-sync) plus a profiling-command lookup and
possible status updates — so `W` is on the order of tens of milliseconds:

| Heartbeat hold time `W` | Busy connections `L` at 1000 QPS |
| --- | --- |
| 30 ms | 30 |
| 50 ms | 50 |
| 100 ms | 100 |
| 150 ms | 150 |

Add read traffic on top. Coarse read scopes now serve from the store in ~10 ms
(negligible), but the **live fine scopes hold a connection for seconds**
(container ~4 s, process ~8 s), so each concurrent fine-scope request consumes
several connection-seconds. Budget generously for these.

Target total provisioned concurrency at **2–3× the computed `L`** so bursts and
slow reads don't exhaust the pool. Measure `W` from your own metrics
(`pg_stat_activity`, request latency) and re-derive — the table is a starting
estimate.

> **Connections enable parallelism, they do not create DB throughput.** 1000
> write-heavy heartbeats/s is real load on the Aurora writer regardless of how
> many connections you open. If the writer saturates (CPU, lock/WAL), the fix is
> to cut per-heartbeat cost (batch the inventory writes) or scale the DB — not to
> add more connections.

## Recommended production settings

Start here, then adjust based on measured `W` and replica count:

```bash
# Remove the per-worker serialization (primary fix).
GPROFILER_POSTGRES_CONN_PER_THREAD=TRUE

# Per-worker connection cap. Sized for ~1000 heartbeat QPS with headroom.
GPROFILER_WEBAPP_THREAD_POOL_SIZE=40

# Process-level concurrency. Workers are I/O-bound on the DB, so exceeding
# core count is fine; raise if still throughput-bound.
GUNICORN_PROCESS_COUNT=16
```

This gives `16 × 40 = 640` parallel DB slots **per replica**. Across replicas,
check the total against `max_connections`:

| Config | Conns/replica | 3 replicas | 6 replicas |
| --- | --- | --- | --- |
| `CONN_PER_THREAD=TRUE`, 8 workers, pool 40 | 320 | 960 | 1920 |
| `CONN_PER_THREAD=TRUE`, 16 workers, pool 40 | 640 | 1920 | 3840 |
| `CONN_PER_THREAD=TRUE`, 16 workers, pool 20 | 320 | 960 | 1920 |

At `max_connections = 5000` even the largest row leaves headroom, but if you
scale replicas hard, keep `replicas × workers × pool` under the limit (with
margin for the periodic tasks and admin connections) — lower
`GPROFILER_WEBAPP_THREAD_POOL_SIZE` or add a pooler (pgbouncer) if you approach
it.

## Verifying

Check live connection usage against the limit:

```sql
SHOW max_connections;
SELECT count(*) AS total,
       count(*) FILTER (WHERE state = 'active') AS active
FROM pg_stat_activity;
```
