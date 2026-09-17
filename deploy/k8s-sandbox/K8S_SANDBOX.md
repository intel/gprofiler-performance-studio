# Kubernetes sandbox (real workload/pod/container scoping)

A self-contained, disposable **Kubernetes** environment that runs the full
Performance Studio stack **plus a real gProfiler agent DaemonSet** and a set of
tenant workloads, so the workload-level profiling flow can be exercised against a
**genuine cluster topology**.

> **This page is the operational runbook.** For the architecture, the
> "what is kind" primer, and the pods-vs-systemd topology breakdown, see
> [`docs/K8S_SANDBOX.md`](../../docs/K8S_SANDBOX.md).

This is a *separate layer* from the docker-compose harness in
[`deploy/E2E_HARNESS.md`](../E2E_HARNESS.md) — it does not replace it. Use them
for different jobs:

| Layer | Orchestrator | Best at | Can't do |
|-------|--------------|---------|----------|
| `deploy/Makefile.e2e` (compose) | Docker Compose | fast API + full S3→SQS→indexer→ClickHouse→flamegraph pipeline smoke | no real namespaces/pods/containers (no CRI) |
| `deploy/k8s-sandbox` (this) | kind / minikube | **real namespace/pod/container/process inventory + scope resolution** | heavier, slower inner loop |

## Why this exists (the one thing compose cannot do)

Workload-level profiling resolves **namespace / pod / container / process**
selections. The agent builds that inventory in
`gprofiler/metadata/heartbeat_metadata.py` by asking `granulate_utils`'
`ContainersClient` to enumerate the node's containers and reading the kubelet
labels `io.kubernetes.pod.namespace`, `io.kubernetes.pod.name`,
`io.kubernetes.container.name`.

`ContainersClient` talks to the **container-runtime socket** — CRI at
`/run/containerd/containerd.sock` (or `/var/run/crio/crio.sock`) and/or Docker —
**not** the Kubernetes API server. Under docker-compose there is no such socket
for the agent, so it logs `No container runtime found for heartbeat workload
inventory` and the pod/container/namespace tabs are exercised only with
*synthetic* heartbeats. On a real node the socket exists, so the inventory is
**real**.

### How the DaemonSet reaches the socket

`granulate_utils` resolves the socket path under `HOST_ROOT_PREFIX = /proc/1/root`
(see `granulate_utils/linux/ns.py`). So the mechanism is:

- **`hostPID: true`** → PID 1 in the pod is the host init, so `/proc/1/root` is
  the node root filesystem and `/proc/1/root/run/containerd/containerd.sock` is
  the node's real CRI socket. `hostPID` is also what lets the agent see every
  node PID to map processes → containers (`get_process_container_id`).
- **`privileged: true`** → grants access to that socket and lets py-spy `ptrace`
  the target workloads.

No bind-mount of the socket is required; the two flags above are the whole trick.
See [`manifests/50-agent-daemonset.yaml`](manifests/50-agent-daemonset.yaml).

> **Use the source-built agent.** The container-inventory heartbeat is a fork
> feature, so the public `intel/gprofiler:latest` image will **not** populate the
> pod/container tabs. `k8s-agent-build` builds it from the sibling `../../gprofiler`
> checkout (reusing `deploy/e2e/agent-glibc.Dockerfile`).

## Architecture

```
 kind / minikube node (containerd)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ ns team-a: checkout(x2), web     ns team-b: payments, search(app+car)  │
 │        ▲ enumerated via CRI (/proc/1/root/run/containerd/...)          │
 │ gprofiler-agent DaemonSet ──heartbeat/commands──► webapp ──► postgres  │
 │  (hostPID, privileged)                 │                               │
 │                                        └── upload ──► S3 (LocalStack)  │
 │                                                          ▼            │
 │                                              SQS ──► ch-indexer ──► ClickHouse
 │                                                          ▼            │
 │                                              nginx NodePort :30443 (UI) │
 └──────────────────────────────────────────────────────────────────────┘
```

Everything is in the `perf-studio` namespace except the tenant workloads
(`team-a`, `team-b`). Only the optional nginx edge is published (NodePort 30443);
the agent and the in-cluster test Job reach `http://webapp` directly.

## Prerequisites

- **Docker**, plus **`kind`** (recommended) or **`minikube`**, and **`kubectl`**.
- **`python3`** on your host (used to parse the minted profiler token).
- The **agent repo** checked out at `../../../gprofiler` (sibling of the studio
  repo) for `k8s-agent-build`.
- TLS certs + `.htpasswd` in `deploy/` (same one-time step as the compose
  harness — see [`deploy/E2E_HARNESS.md`](../E2E_HARNESS.md#prerequisites)).

## Quick start

```bash
cd deploy/k8s-sandbox

# One-shot: create cluster, build+load images, deploy stack+workloads+agent, mint token.
make -f Makefile.k8s k8s-all

# Give the agent ~30-60s to enumerate CRI, then inspect the live inventory.
make -f Makefile.k8s k8s-status

# Run the real-topology acceptance suite (AT-K1..K5).
make -f Makefile.k8s k8s-test

# Drive the control plane against the real agent.
make -f Makefile.k8s k8s-start
make -f Makefile.k8s k8s-stop

# Open the console (basic auth admin/admin).
make -f Makefile.k8s k8s-url

# Tear the whole sandbox down.
make -f Makefile.k8s k8s-down-all
```

Use `CLUSTER=minikube` on any target to use minikube instead of kind:

```bash
make -f Makefile.k8s k8s-all CLUSTER=minikube
```

`make -f Makefile.k8s help` lists all targets.

## What the acceptance suite proves (AT-K1..K5)

[`tests/test_k8s_inventory.py`](tests/test_k8s_inventory.py), run in-cluster as a
Job against the live `webapp`:

- **AT-K1** — the real agent DaemonSet registers as a host under service
  `k8s-sandbox`.
- **AT-K2** — tenant **namespaces** (`team-a`, `team-b`) appear in the namespace
  scope (discovered from CRI, not fabricated).
- **AT-K3** — **pods** for each workload (`checkout`, `web`, `payments`,
  `search`) appear in the pod scope.
- **AT-K4** — **containers** appear, including *both* containers of the
  2-container `search` pod (`search-app`, `search-sidecar`).
- **AT-K5** — a host-scope start/stop resolves the **real** agent host (from live
  inventory) and is accepted — command creation against an actual agent.

The suite reuses the compose suite's HTTP harness (`src/tests/e2e/harness.py`) so
the request/response contract lives in one place, and matches on serialized
inventory (not hard-coded per-scope key casing) so it stays robust as the node
also contains system/studio containers.

## Files

| Path | Purpose |
|------|---------|
| `Makefile.k8s` | cluster/build/load/deploy/token/test/start/stop/down targets |
| `kind-config.yaml` | single-node kind cluster; publishes nginx NodePort 30443 |
| `manifests/00-namespaces.yaml` | `perf-studio`, `team-a`, `team-b` |
| `manifests/01-config.yaml` | shared `studio-config` ConfigMap + `studio-secrets` |
| `manifests/10-datastores.yaml` | Postgres + ClickHouse (schema via init ConfigMaps) |
| `manifests/12-localstack.yaml` | S3 + SQS emulator (init from ConfigMap) |
| `manifests/13-ch-rest-service.yaml` | ClickHouse REST facade (TLS from Secret) |
| `manifests/20-webapp.yaml` | FastAPI backend + UI (`http://webapp`) |
| `manifests/21-ch-indexer.yaml` | SQS→ClickHouse indexer |
| `manifests/22-logs-backend.yaml` | agent-logs + periodic-tasks (shared `/logs`) |
| `manifests/30-nginx.yaml` | optional TLS/basic-auth edge (NodePort 30443) |
| `manifests/40-workloads.yaml` | tenant workloads the agent enumerates |
| `manifests/50-agent-daemonset.yaml` | **the real agent (hostPID + privileged)** |
| `tests/` | in-cluster acceptance Job + real-topology tests |

## Notes & caveats

- **kind vs minikube.** kind is the default and recommended for CI (lighter,
  containerd-native, faster boot). minikube is supported for local use via
  `CLUSTER=minikube` (start it with `--container-runtime=containerd`).
- **Inner loop.** Unlike compose (which builds straight from `../src`), a cluster
  requires images to be *loaded* in (`kind load` / `minikube image load`) after
  each rebuild — re-run `k8s-images && k8s-load` (or `k8s-agent-build && k8s-load`)
  when you change code.
- **Disposable.** The cluster is hermetic: LocalStack fakes AWS and nothing
  leaves the node. `k8s-down-all` deletes the cluster and leaves no residue.
- **The agent enumerates the whole node**, so inventory also contains
  `kube-system`/studio containers — expected. The tests assert on the specific
  tenant entities rather than exact totals.
- **Low ports as non-root.** The webapp and agents-logs-backend images run as a
  non-root user and bind port 80. Docker permits this via its default
  `net.ipv4.ip_unprivileged_port_start=0`; Kubernetes does not, so those pods set
  that (safe) sysctl in their `securityContext`. If your kubelet restricts safe
  sysctls, allowlist `net.ipv4.ip_unprivileged_port_start` (or run those two as
  root).

## Verified

Brought up on a single-node **kind v1.30** cluster (containerd 1.7) and confirmed
end to end:

- The agent DaemonSet connects and heartbeats with **no** `No container runtime
  found` error (contrast the compose harness), i.e. it reached the node's CRI
  socket via `/proc/1/root` with `hostPID` + `privileged`.
- `workload_status` reported real topology — `tabCounts` `{service:1, host:1,
  namespace:5, pod:23, container:25, process:93}` — including the tenant
  namespaces `team-a`/`team-b` and the 2-container `search` pod resolved as
  distinct `search-app` + `search-sidecar` containers.
- The full acceptance suite passed: `AT-K1..K5` (5 passed).
- **Full artifact pipeline closed in-cluster**: a host-scope start made the agent
  profile the real workloads and upload; the webapp wrote the collapsed stacks to
  S3 (`products/k8s-sandbox/stacks/...gz`) and enqueued SQS; the indexer consumed
  it, inserted 27 rows into `flamedb.samples`, and wrote the rendered
  `..._adhoc_flamegraph.html` back to S3 — all against LocalStack, no real AWS.

Two k8s-specific fixes came out of that run (both committed):

- **Non-root low-port bind** (webapp, agents-logs-backend) — added the
  `net.ipv4.ip_unprivileged_port_start=0` sysctl (above).
- **Indexer startup ordering** — compose gated it on `localstack: service_healthy`;
  k8s has no `depends_on` and the indexer resolves the SQS URL once without
  retry, so it can boot before LocalStack and never consume. Added an
  init-container that waits for LocalStack's SQS to report running.
