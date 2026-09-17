# End-to-end test harness (Performance Studio + real gProfiler agent)

This harness runs the **full** Performance Studio stack **plus a real gProfiler
agent** locally, so the dynamic/workload-level profiling flow can be exercised
end to end — including the S3 → SQS → indexer → ClickHouse → flamegraph pipeline
that the studio-only setup never touches.

```
 e2e-sample-app (CPU workload)
        ▲ profiled by
 gprofiler-agent ──heartbeat/commands──► webapp (backend)  ──► Postgres
        │                                     │
        └──upload profile (/api/v2/profiles)──┘
                                              ▼
                                    S3 (LocalStack) ──► SQS (LocalStack)
                                                          ▼
                                             ch-indexer ──► ClickHouse (flamedb)
                                                          ▼
                                              UI / flamegraph API (nginx :4433)
```

> **Where this fits.** This harness is **Layer 2** of a three-layer test setup
> (fast unit → this compose harness → a kind/minikube Kubernetes sandbox). See
> [The three-layer test harness](#the-three-layer-test-harness) below for how the
> layers differ and how to invoke each. Layer 3 lives in
> [`k8s-sandbox/`](k8s-sandbox/K8S_SANDBOX.md) (architecture:
> [`../docs/K8S_SANDBOX.md`](../docs/K8S_SANDBOX.md)).

## Files

| File | Purpose |
|------|---------|
| `docker-compose.e2e.yml` | Overlay adding `e2e-sample-app`, `gprofiler-agent`, `e2e-tests`, `e2e-ui-tests` |
| `Makefile.e2e` | `up / up-src / status / start / stop / flamegraph / test / ui-test / down` targets |
| `e2e/agent-glibc.Dockerfile` | Wraps a source-built (`--fast`) agent exe in a glibc base |
| `../src/tests/e2e/` | In-network pytest API acceptance runner (AT-S1..S15) |
| `../src/tests/playwright/` | Playwright UI acceptance runner |

## Container architecture

**It is not one container and not a Kubernetes pod.** It is a set of independent
Docker containers wired together by Docker Compose on a single user-defined
bridge network (`<project>_default`, i.e. `deploy_default`). Each service is its
own container running one process; they find each other by **service name** as a
DNS hostname on that network. There is no orchestrator (no k8s, no pod spec) —
just Compose.

| Container | Image / build | Role |
|-----------|---------------|------|
| `gprofiler-ps-webapp` | built from `../src` | FastAPI backend + built UI (heartbeat, profile ingest, status APIs) |
| `gprofiler-ps-nginx-load-balancer` | `nginx:1.23.3` | TLS + basic-auth edge; publishes `:4433`/`:8443` to the host |
| `gprofiler-ps-postgres` | `postgres` | heartbeat inventory, profiling requests/commands |
| `gprofiler-ps-clickhouse` | `clickhouse` | `flamedb` sample/metric storage (profile `with-clickhouse`) |
| `gprofiler-ps-ch-rest-service` | built | ClickHouse REST facade for the backend |
| `gprofiler-ps-ch-indexer` | built | **SQS consumer**: reads S3 profiles → writes ClickHouse |
| `gprofiler-ps-agents-logs-backend` | built | agent log ingest |
| `gprofiler-ps-periodic-tasks` | built | background jobs |
| `gprofiler-ps-localstack` | `localstack/localstack:3.0` | **one** container emulating **S3 + SQS** |
| `gprofiler-ps-e2e-sample-app` | `python:3.11-slim` | deterministic CPU workload to profile *(harness)* |
| `gprofiler-ps-e2e-agent` | source-built or `GPROFILER_IMAGE` | real gProfiler agent in heartbeat mode *(harness)* |
| `gprofiler-ps-e2e-tests` | built from `../src/tests/e2e` | pytest API acceptance runner, profile `test` *(harness)* |
| `gprofiler-ps-e2e-ui-tests` | official Playwright image | Playwright UI runner, profile `ui` *(harness)* |

Only nginx publishes host ports; everything else talks over the internal
network. The agent, for example, reaches the backend at `http://webapp` directly
(no host port, no nginx auth).

## S3 + SQS via LocalStack (no AWS account needed)

The `localstack` container runs the S3 and SQS emulators in-process
(`SERVICES=s3,sqs`) and exposes a single gateway on `:4566`. On startup it runs
every script in `deploy/localstack_init/` — `01_init_s3_sqs.sh` creates the
bucket and queue and wires S3 event notifications into SQS. A healthcheck gates
dependents until both services report `running`.

The pipeline then flows entirely inside the network:

1. agent uploads a profile to `webapp` (`/api/v2/profiles`)
2. `webapp` writes the object to **S3** (`s3://performance-studio-bucket/...`)
3. S3 emits an event to **SQS** (`performance-studio-queue`)
4. `ch-indexer` consumes the SQS message, reads the object, and writes rows to
   **ClickHouse** (`flamedb.samples`) plus the flamegraph HTML back to S3

All AWS SDK clients in the stack point at `AWS_ENDPOINT_URL=http://localstack:4566`
with dummy `test`/`test` credentials, so nothing touches real AWS.

## Prerequisites

- **Docker + Docker Compose v2** (Linux, or macOS/Windows via Docker Desktop).
- The **`gprofiler` agent repo** checked out as a sibling of this repo
  (`../../gprofiler`) — required for `e2e-up-src` (the portable agent path).
- **TLS cert + basic-auth file** for nginx (one-time, in `deploy/`):

```bash
cd deploy
mkdir -p tls
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout tls/key.pem -out tls/cert.pem
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout tls/ch_rest_key.pem -out tls/ch_rest_cert.pem
htpasswd -B -C 12 -c .htpasswd admin      # set the password to 'admin' to match the defaults
```

The harness assumes web creds `admin` / `admin` (override with `AUTH=` on the
Make targets and the `E2E_BASIC_AUTH_*` env vars).

> **Note:** The `htpasswd` command above uses `-c` which *creates* (or overwrites)
> `.htpasswd`. If you already have a `.htpasswd` with a different username, the
> `admin` entry won't be present and every `make` target that calls the nginx API
> will get a `401`. Either recreate the file with `-c`, or add the entry without
> overwriting: `htpasswd -B -C 12 -b .htpasswd admin admin`.

## Quick start

```bash
cd deploy

# Bring up studio + sample app + agent (mints a valid profiler token for you).
make -f Makefile.e2e e2e-up

# See the agent's live inventory row (heartbeat, agent version, status).
make -f Makefile.e2e e2e-status

# Drive the control plane:
make -f Makefile.e2e e2e-start     # host-scope START (profiles the sample app)
make -f Makefile.e2e e2e-stop      # host-scope STOP  (no PIDs at host level)

# Inspect the artifacts the pipeline produced in (Local)S3.
make -f Makefile.e2e e2e-flamegraph

# Follow the agent.
make -f Makefile.e2e e2e-agent-logs

# Remove ONLY the harness services (studio keeps running).
make -f Makefile.e2e e2e-down
```

`SERVICE=<name>` overrides the target service (default `e2e-sample-app`) on the
`e2e-start` / `e2e-stop` / `e2e-flamegraph` targets.

## How the agent is wired

- **Endpoint / auth.** The agent points at the *internal* `webapp` service
  (`--server-host=http://webapp --api-server=http://webapp`), which bypasses the
  nginx basic-auth that guards the browser UI. Heartbeat/command endpoints don't
  validate the bearer token locally, but the upload/health-check path *does* — so
  `e2e-up` mints a real token via `GET /api/api_key` and injects it as
  `GPROFILER_TOKEN`.
- **Isolation.** The agent shares only the **sample app's** PID namespace
  (`pid: "service:e2e-sample-app"`), so it profiles that workload and never the
  host. `perf` is disabled (`--perf-mode=none`); py-spy profiles the Python
  workload.
- **Determinism.** `e2e-sample-app` runs a fixed hot loop, so flamegraphs have
  stable, recognizable frames.

## Agent image

There are two ways to get the agent image; pick per your goal.

### A) From source, fast (verify your agent changes) — recommended

Uses the agent repo's **`--fast`** executable build, which skips `staticx`
(the slow bundling step) and finishes in ~1-2 min on a warm Docker cache:

```bash
make -f Makefile.e2e e2e-up-src        # builds exe (--fast) + wraps + brings up
# or just rebuild the image:
make -f Makefile.e2e e2e-agent-build
```

Because `--fast` skips staticx, the resulting `build/<arch>/gprofiler` is
**glibc-dynamic** and will *not* run on the alpine base in the repo's
`container.Dockerfile` (you'd get `exec /gprofiler: No such file or directory`).
The harness therefore wraps it in a glibc base — see `e2e/agent-glibc.Dockerfile`.
Override arch/repo with `AGENT_ARCH=` / `AGENT_REPO=` if needed.

### B) Prebuilt image (fastest, no build)

`make -f Makefile.e2e e2e-up` uses `GPROFILER_IMAGE` (default
`intel/gprofiler:latest`, the upstream public image) with the vanilla
`/gprofiler` entrypoint. Good for exercising the studio side when you don't need
agent-source changes. Override it to test a specific build:

```bash
GPROFILER_IMAGE=intel/gprofiler:1.53.1 make -f Makefile.e2e e2e-up
```

Agent-side pure-logic changes (heartbeat inventory, command queue) are also
covered by the fast unit suite in `gprofiler/tests_fast/`.

## Portability (will it work on any engineer's box?)

Yes for **Linux/Ubuntu** with Docker + Compose v2 — that's the primary target and
where it's verified. Keep these in mind:

- **Agent image.** `e2e-up` defaults to the upstream public `intel/gprofiler:latest`.
  To verify *your own* agent changes, use `make -f Makefile.e2e e2e-up-src`, which
  builds the agent from the sibling `../../gprofiler` checkout. Studio images all
  build from source here, so the studio side is portable as-is.
- **CPU architecture.** The source build defaults to `x86_64`
  (`build_x86_64_executable.sh`). On arm64 (Apple Silicon, Graviton) use
  `AGENT_ARCH=aarch64 make -f Makefile.e2e e2e-up-src` (drives
  `build_aarch64_executable.sh`); the glibc wrapper honors `AGENT_ARCH`.
- **Linux vs macOS/Windows.** On Linux the agent's `privileged: true` + shared
  PID namespace + py-spy `ptrace` work natively. On Docker Desktop
  (macOS/Windows) everything runs inside its Linux VM and works, but profiling
  fidelity depends on the VM; `--perf-mode=none` (already set) avoids kernel-perf
  issues. `pid: "service:..."` is a Compose feature and is portable.
- **Host ports.** Only nginx publishes ports (`4433`, `8443`). If those clash,
  remap them in `docker-compose.yml`. The DB ports are intentionally not
  published (tests run in-network), so there's nothing else to collide.
- **Compose network name.** Helper targets use `$(NETWORK)`, derived from the
  project dir (`deploy_default`). If you set `COMPOSE_PROJECT_NAME`, pass
  `NETWORK=<name>_default`.
- **Prerequisites** above (TLS + `.htpasswd`) are one-time and cross-platform
  (need `openssl` + `htpasswd`; `htpasswd` ships with `apache2-utils` on Ubuntu).

## The three-layer test harness

Three layers test the workload-level profiling flow at increasing fidelity. The
key difference between layers is **how the workload inventory is produced** —
fabricated in-code, POSTed as synthetic heartbeats, or enumerated for real from a
Kubernetes node's container runtime.

| Layer | What runs | Inventory source | Proves | Invoke |
|-------|-----------|------------------|--------|--------|
| **1. Fast unit/spec** | no stack | in-code fixtures | backend/agent pure logic (PR gate) | `pytest` / `node --test` |
| **2. Compose harness** (this doc) | full studio via Docker Compose | **synthetic** heartbeats (+ real-agent pipeline) | studio logic + S3→SQS→indexer→ClickHouse→flamegraph | `make -f Makefile.e2e …` |
| **3. kind/minikube sandbox** | full studio on Kubernetes | **real** CRI enumeration by a DaemonSet | real namespace/pod/container/process discovery + scoping | `make -f Makefile.k8s …` |

### Layer 1 — fast unit/spec (no stack, PR gate)

No services required; runs in seconds.

```bash
# studio backend spec (request builder, PMU/capacity, profiling-request logic)
pytest -q gprofiler-performance-studio/src/tests/spec
# studio frontend unit tests
cd gprofiler-performance-studio/src/gprofiler/frontend && node --test
# agent-side fast logic (heartbeat inventory, command queue) — in the agent repo
pytest -q gprofiler/tests_fast
```

### Layer 2 — compose harness (this doc)

Full studio + a real agent profiling a deterministic sample app, plus the
complete artifact pipeline. Three test families:

- **API acceptance `AT-S1..S15`** — 15 in-network pytest cases (`src/tests/e2e/`)
  driving the live stack with **synthetic** heartbeats: inventory/tab-counts
  (S1–S4), host/service/process resolution + command creation (S5–S7),
  empty-resolution 422 (S8), PMU rejection (S9), continuous-subscription
  auto-enrollment (S10–S13), legacy/partial-inventory compatibility (S14–S15).
- **Full-pipeline smoke `AT-A1..A8`** — the real source-built agent proves
  S3 → SQS → indexer → ClickHouse → flamegraph.
- **Playwright UI e2e** — drives the console through nginx (basic auth +
  self-signed TLS), asserting the start/stop confirmation flow (the STOP case is
  the regression test for the host-level-stop bug).

```bash
cd deploy
make -f Makefile.e2e e2e-up            # bring up (or e2e-up-src for source-built agent)
make -f Makefile.e2e e2e-test          # AT-S1..S15 API acceptance
make -f Makefile.e2e e2e-start \
  && make -f Makefile.e2e e2e-flamegraph   # AT-A1..A8 pipeline smoke (inspect artifacts)
make -f Makefile.e2e e2e-ui-test       # Playwright UI acceptance
make -f Makefile.e2e e2e-down          # remove harness (studio keeps running)
```

### Layer 3 — kind/minikube sandbox (real Kubernetes topology)

The one thing compose can't do: real namespaces/pods/containers. A gProfiler
agent **DaemonSet** on a real node reads the node's CRI socket and enumerates
genuine workloads, so this layer proves discovery + scope resolution under
Kubernetes. Tests: **`AT-K1..K5`** (agent registers as host; tenant namespaces,
pods, and containers — incl. a 2-container pod — discovered from real CRI;
host-scope start dispatches to the real agent). Full details:
[`k8s-sandbox/K8S_SANDBOX.md`](k8s-sandbox/K8S_SANDBOX.md) (architecture +
rationale: [`../docs/K8S_SANDBOX.md`](../docs/K8S_SANDBOX.md)).

```bash
cd deploy/k8s-sandbox

# --- kind (default, recommended: lightweight, containerd-native) ---
make -f Makefile.k8s k8s-all           # cluster + build + load + deploy + token
make -f Makefile.k8s k8s-test          # AT-K1..K5 real-topology acceptance
make -f Makefile.k8s k8s-status        # live inventory across all scopes
make -f Makefile.k8s k8s-url           # -> https://localhost:30443 (admin/admin)
make -f Makefile.k8s k8s-down-all      # delete the whole cluster
```

**Option: minikube instead of kind.** The same manifests, agent DaemonSet, and
`AT-K1..K5` suite run unchanged on minikube — only cluster lifecycle, image
loading, and the URL differ. Select it with `CLUSTER=minikube`, and use a distinct
`CLUSTER_NAME` if a kind cluster is already running (kind binds host port `30443`;
map minikube elsewhere, e.g. `--ports=30444:30443`, to avoid a collision):

```bash
cd deploy/k8s-sandbox
make -f Makefile.k8s k8s-all  CLUSTER=minikube CLUSTER_NAME=gprofiler-mk
make -f Makefile.k8s k8s-test CLUSTER=minikube CLUSTER_NAME=gprofiler-mk
make -f Makefile.k8s k8s-url  CLUSTER=minikube CLUSTER_NAME=gprofiler-mk  # -> https://<minikube ip>:30443
make -f Makefile.k8s k8s-down-all CLUSTER=minikube CLUSTER_NAME=gprofiler-mk
```

> **Caveat (why kind is the default).** With `--container-runtime=containerd`
> minikube gives the same prod-like CRI path, but its **docker driver may fail to
> boot on some hosts** (e.g. Docker 28 + cgroup v2 + newer kernels, where the node
> container can't start systemd), while kind's `kindest/node` boots there fine. If
> minikube won't start, use kind. See the "Challenge" section in
> [`../docs/K8S_SANDBOX.md`](../docs/K8S_SANDBOX.md) for the full write-up.

## Optional: container/pod inventory

The agent logs `No container runtime found for heartbeat workload inventory`
because the Docker socket isn't mounted (keeps it isolated from the host). To
exercise namespace/pod/container scope tabs with a real agent, mount
`/var/run/docker.sock:/var/run/docker.sock:ro` into `gprofiler-agent` — note this
gives the agent visibility into all host containers.

For **real** Kubernetes namespace/pod/container/process inventory (not the Docker
socket workaround), use **Layer 3** — the kind/minikube sandbox — which runs an
agent DaemonSet against a real node's CRI. See
[The three-layer test harness](#the-three-layer-test-harness).

## Notes

- `e2e-down` removes only the harness containers (agent, sample app, test/UI
  runners); use `e2e-down-all` to tear down the entire studio stack (destructive).
- **Token minting on cold builds.** `e2e-up` polls the studio API for up to 60 s
  (30 × 2 s) before minting the agent token. On a cold build the webapp can take
  longer, leaving the agent container with an empty `GPROFILER_TOKEN` and causing
  it to crash-loop. If this happens the rest of the stack is still healthy — just
  re-run the mint + recreate step manually:
  ```bash
  tok=$(curl -sk https://localhost:4433/api/api_key -u admin:admin \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['apiKey'])")
  GPROFILER_TOKEN="$tok" GPROFILER_IMAGE=gprofiler-e2e-agent:src \
    docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    --profile with-clickhouse up -d --force-recreate gprofiler-agent
  ```
- The compose project name defaults to the directory (`deploy`), so the network
  is `deploy_default`. Helper targets read `$(NETWORK)`; override with
  `NETWORK=<project>_default` if you set `COMPOSE_PROJECT_NAME`.
