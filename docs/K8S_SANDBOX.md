# Kubernetes sandbox for workload-level profiling

Architecture and rationale for the local Kubernetes sandbox that validates
workload-level (namespace / pod / container / process) profiling against a
**real cluster topology**.

> **Operational runbook** (prerequisites, `make` targets, quick start) lives next
> to the code: [`deploy/k8s-sandbox/K8S_SANDBOX.md`](../deploy/k8s-sandbox/K8S_SANDBOX.md).
> This page is the conceptual/architecture companion.

## Why a Kubernetes sandbox (and not just docker-compose)

The compose harness ([`deploy/E2E_HARNESS.md`](../deploy/E2E_HARNESS.md)) runs the
full stack fast and exercises the S3→SQS→indexer→ClickHouse→flamegraph pipeline,
but it **cannot** produce real namespaces/pods/containers. Workload-level
profiling resolves those scopes, and the agent builds that inventory in
`gprofiler/metadata/heartbeat_metadata.py` by asking `granulate_utils`'
`ContainersClient` to enumerate the node's containers via the **container-runtime
socket** (CRI at `/run/containerd/containerd.sock`, or Docker) — **not** the
Kubernetes API server. It reads the kubelet labels
`io.kubernetes.pod.namespace`, `io.kubernetes.pod.name`,
`io.kubernetes.container.name` off each container.

Under docker-compose there is no such socket for the agent, so it logs
`No container runtime found for heartbeat workload inventory` and the
pod/container/namespace tabs are only exercised with *synthetic* heartbeats. On a
real node the socket exists, so the inventory is **real**. That gap is the reason
this sandbox exists.

| Layer | Orchestrator | Proves | Can't do |
|-------|--------------|--------|----------|
| `deploy/Makefile.e2e` (compose) | Docker Compose | fast API + full artifact pipeline | no real namespaces/pods/containers |
| `deploy/k8s-sandbox` (this) | kind / minikube | **real namespace/pod/container/process inventory + scope resolution** | heavier, slower inner loop |

## What is a kind cluster?

**kind = "Kubernetes IN Docker."** The entire cluster *node* is itself a single
Docker container running the `kindest/node` image. Inside that container, an init
system (systemd) boots a container runtime and the kubelet, and Kubernetes then
runs all workloads as pods *inside* the node container. It is nested containers:

```
Your Linux host
└─ Docker
   └─ kind node  (container: kindest/node:v1.30.0)   <- "the cluster"
      ├─ systemd (PID 1)
      │   ├─ containerd.service     ← the CRI runtime that runs every pod
      │   ├─ kubelet.service        ← node agent: talks to the API server, drives containerd
      │   └─ systemd-journald
      └─ pods (run by containerd, orchestrated by Kubernetes)
```

Both kind and minikube give a **hermetic, disposable** cluster: create → test →
destroy, nothing touches real infrastructure. The `Makefile.k8s` supports either
via `CLUSTER=kind|minikube` (see [the runbook](../deploy/k8s-sandbox/K8S_SANDBOX.md)).

## kind vs. minikube (and why kind is the default)

Both create a throwaway local Kubernetes cluster; the difference is *how* the node
is run and which container runtime lives inside it — which matters a lot here,
because the whole point of this sandbox is that the agent reads the node's **CRI
socket**.

| | **kind** | **minikube** |
|---|---|---|
| Name | "Kubernetes **IN D**ocker" | "mini Kubernetes" |
| Node runs as | a Docker container (`kindest/node`) | a VM *or* a container ("drivers": docker, kvm2, virtualbox, none, …) |
| Runtime inside node | **containerd** (native) — socket at `/run/containerd/containerd.sock` | docker by default; containerd only with `--container-runtime=containerd` |
| Install | single static binary, needs Docker | single binary, but drivers add moving parts |
| Weight / speed | very light, fast, CI-standard | heavier; more features (addons, dashboard, LoadBalancer tunnels) |
| Best fit | automated testing / CI | general local dev with extras |

Why kind is the default for this sandbox:

1. **containerd-native, prod-like path.** A real production node runs containerd
   and exposes the CRI socket the agent reads (`/run/containerd/containerd.sock`).
   kind gives exactly that out of the box. minikube's default docker driver would
   hand the agent `docker.sock` instead — a different, less prod-like code path —
   unless you explicitly pass `--container-runtime=containerd`.
2. **Lighter + fewer choices.** One binary, only needs Docker; no VM/driver
   matrix to reason about.
3. **CI-standard.** Easiest to graduate this sandbox into CI later.

minikube is **not wrong** — with `--container-runtime=containerd` it produces the
same containerd CRI topology and the manifests/tests are identical. It's just
heavier and has more environment-specific setup.

### Isolation model: VM drivers vs container drivers (and why no VM here)

A common assumption is "minikube = an isolated VM." That was minikube's original
design, but today its isolation depends on the **driver**:

- **VM drivers** (`kvm2`, `virtualbox`, `hyperkit`, `hyper-v`, `qemu`) boot a real
  virtual machine with its **own kernel** — the strongest isolation, and
  minikube's genuine edge over kind *when a hypervisor is available*.
- **Container drivers** (`docker`, `podman`) run the node as a **container sharing
  the host kernel** — the same model as kind (which is *always* a container).
- **`none`** runs the kubelet directly on the host (no isolation).

Either way the *cluster* is hermetic and disposable; what differs is whether the
boundary is a separate kernel (VM) or a shared-kernel container.

**Why this host only offers the container driver.** The build host is a standard
(non-`.metal`) AWS EC2 instance — itself a guest VM that does **not expose nested
virtualization**: there is no `/dev/kvm`, `/proc/cpuinfo` shows zero `vmx`/`svm`
flags, and `systemd-detect-virt` reports `amazon`. A VM driver needs hardware
virtualization (VT-x/AMD-V) passed through to the guest, so `kvm2`/`virtualbox`
cannot run — only the `docker` (container) driver is viable. That is why minikube
here has the *same* shared-kernel boundary as kind and hits the same
systemd-in-container problem described in the Challenge below. To get a true
minikube VM on AWS you need a **bare-metal instance type** (e.g. `*.metal`), which
exposes the CPU virtualization extensions to the guest.

## Challenge: minikube's docker driver won't boot on this host

`CLUSTER=minikube` is fully wired into `Makefile.k8s`, but when validated on the
build host it could **not** bring up a cluster. Documented here so the next person
doesn't burn time rediscovering it.

**Symptom.** `minikube start --driver=docker --container-runtime=containerd`
creates the `kicbase` node container, which then exits immediately at
`exec /sbin/init`:

```
+ exec /sbin/init
Couldn't find an alternative telinit implementation to spawn.: container exited unexpectedly
X Exiting due to GUEST_PROVISION_EXIT_UNEXPECTED: Failed to start host ...
```

i.e. systemd cannot come up as PID 1 inside minikube's node container, so the
kubelet/API server never start.

**What was tried (all reproduced the same failure):**

| Attempt | Result |
|---------|--------|
| current kicbase `v0.0.50` (Ubuntu 24.04) + containerd | `exec /sbin/init` exits |
| older kicbase `v0.0.44` + `--kubernetes-version=v1.30.0` | same |
| `--force-systemd` | same |

**Root cause.** minikube's node image can't run systemd-as-PID-1 in this
particular **Docker 28.x + cgroup v2 + AWS `6.8.0` kernel** combination — the
container's init bails before systemd takes over. Notably, kind's
`kindest/node:v1.30.0` boots systemd fine on the *exact same host* (that's what
the running sandbox uses), so this is specific to how minikube constructs/runs its
node container, not a general "systemd-in-container is impossible here" problem.

**Why the other minikube drivers weren't used.** VM drivers (`kvm2`,
`virtualbox`) need nested virtualization this cloud VM doesn't expose; the `none`
driver installs the kubelet **directly on the host** (invasive, root-level, would
mutate the host) and was intentionally avoided. That leaves the docker driver as
the only in-scope option — and it's the one that fails.

**Resolution / takeaway.** Use **kind** here (the default). On a laptop or CI
runner where minikube's docker driver boots normally, `CLUSTER=minikube` works
with the *same* manifests and acceptance suite — nothing else changes. This is the
concrete, practical reason kind is the default for this sandbox, beyond the
containerd-native argument above.

## How to use it (kind or minikube)

All flow through `deploy/k8s-sandbox/Makefile.k8s`. Pick the cluster tool with the
`CLUSTER` variable (default `kind`):

```bash
cd gprofiler-performance-studio/deploy/k8s-sandbox

# --- kind (default, recommended) ---
make -f Makefile.k8s k8s-all           # cluster + build + load + deploy + token
make -f Makefile.k8s k8s-test          # AT-K1..K5 real-topology acceptance
make -f Makefile.k8s k8s-status        # live workload inventory (all scopes)
make -f Makefile.k8s k8s-url           # -> https://localhost:30443 (admin/admin)
make -f Makefile.k8s k8s-down-all      # delete the whole cluster

# --- minikube (same manifests/tests; needs a host where its docker driver boots) ---
make -f Makefile.k8s k8s-all  CLUSTER=minikube CLUSTER_NAME=gprofiler-mk
make -f Makefile.k8s k8s-test CLUSTER=minikube CLUSTER_NAME=gprofiler-mk
make -f Makefile.k8s k8s-url  CLUSTER=minikube CLUSTER_NAME=gprofiler-mk   # -> https://<minikube ip>:30443
make -f Makefile.k8s k8s-down-all CLUSTER=minikube CLUSTER_NAME=gprofiler-mk
```

The only thing `CLUSTER` changes is cluster lifecycle + image loading (`kind load
docker-image` vs `minikube image load`) and the URL; every manifest, ConfigMap,
Secret, the agent DaemonSet, and the acceptance suite are identical. Use a
distinct `CLUSTER_NAME` (e.g. `gprofiler-mk`) if you want to run minikube
alongside an existing kind cluster, and note kind already binds host port `30443`
— map minikube elsewhere (e.g. `--ports=30444:30443`) to avoid a collision.

## Topology: what runs as systemd vs. as pods

This is the key mental model. Inside the kind node, **only three things run under
systemd** — everything else (including Kubernetes' own control plane) runs as
pods managed by the kubelet + containerd:

**systemd services (inside the node container):**

| Unit | Role |
|------|------|
| `containerd.service` | container runtime (CRI) that actually runs all pods |
| `kubelet.service` | node agent; `--container-runtime-endpoint=unix:///run/containerd/containerd.sock` |
| `systemd-journald.service` | logging |

Notably, the kubelet's CRI endpoint is the **exact socket the agent DaemonSet
reads** (via `/proc/1/root`, see below) to enumerate workloads.

**Everything else is a pod:**

- **Kubernetes control plane** (`kube-system`, run as *static pods*):
  `kube-apiserver`, `etcd`, `kube-scheduler`, `kube-controller-manager`, plus
  `kube-proxy`, `kindnet` (CNI), `coredns`, and `local-path-provisioner`.
- **Performance Studio stack** (`perf-studio` namespace): `webapp`, `postgres`,
  `clickhouse`, `ch-rest-service`, `ch-indexer`, `logs-backend` (2 containers),
  `nginx`, `localstack`, and the **`gprofiler-agent` DaemonSet**.
- **Tenant workloads**: `team-a` (`checkout` ×2, `web`) and `team-b`
  (`payments`, `search` — a 2-container pod).

So even etcd and the API server are pods — a kind design choice. Contrast
docker-compose, where each service is a bare container on a bridge network with
**no kubelet, no containerd-as-CRI, and no pods**, which is exactly why the agent
finds "no container runtime" there but discovers real pods/namespaces/containers
here.

## How the agent DaemonSet reaches the CRI socket

`granulate_utils` resolves the socket path under `HOST_ROOT_PREFIX = /proc/1/root`
(`granulate_utils/linux/ns.py`). The mechanism is two pod settings, not a
bind-mount:

- **`hostPID: true`** → PID 1 in the pod is the host (node) init, so
  `/proc/1/root` is the node root filesystem and
  `/proc/1/root/run/containerd/containerd.sock` is the node's real CRI socket.
  `hostPID` also lets the agent see every node PID to map processes → containers.
- **`privileged: true`** → grants access to that socket and lets py-spy `ptrace`
  the target workloads.

> **Use the source-built agent.** The container-inventory heartbeat is a fork
> feature, so the public `intel/gprofiler:latest` image will **not** populate the
> pod/container tabs.

## Data flow

```
 kind node (containerd)
   ns team-a: checkout(x2), web       ns team-b: payments, search(app+sidecar)
          ▲ enumerated via CRI (/proc/1/root/run/containerd/...)
   gprofiler-agent DaemonSet ─ heartbeat/commands ─► webapp ─► postgres
    (hostPID, privileged)               │
                                        └─ upload ─► S3 (LocalStack)
                                                       ▼
                                             SQS ─► ch-indexer ─► ClickHouse
                                                       ▼
                                             nginx NodePort :30443 (UI)
```

## Verified end-to-end

Brought up on a single-node **kind v1.30** cluster (containerd 1.7) and confirmed:

- Agent DaemonSet connects and heartbeats with **no** `No container runtime
  found` error (contrast compose) — it reached the node CRI socket.
- `workload_status` reported real topology — `tabCounts` `{service:1, host:1,
  namespace:5, pod:23, container:25, process:93}` — including tenant namespaces
  `team-a`/`team-b` and the 2-container `search` pod resolved as distinct
  `search-app` + `search-sidecar`.
- Acceptance suite `AT-K1..K5` passed (5/5).
- **Full artifact pipeline closed in-cluster**: a host-scope start made the agent
  profile the real workloads and upload; the webapp wrote collapsed stacks to S3
  (`products/k8s-sandbox/stacks/...gz`) and enqueued SQS; the indexer consumed it,
  inserted 27 rows into `flamedb.samples`, and wrote the rendered
  `..._adhoc_flamegraph.html` back to S3 — all against LocalStack, no real AWS.

Two k8s-specific fixes came out of that run:

- **Non-root low-port bind** (webapp, agents-logs-backend run as non-root and
  bind port 80): Docker allows this via its default
  `net.ipv4.ip_unprivileged_port_start=0`; Kubernetes does not, so those pods set
  that (safe) sysctl explicitly.
- **Indexer startup ordering**: compose gated it on `localstack: service_healthy`;
  k8s has no `depends_on` and the indexer resolves the SQS URL once without retry,
  so it can boot before LocalStack and never consume. An init-container now waits
  for LocalStack's SQS to report running.
