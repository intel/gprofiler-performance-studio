# Spark-on-Kubernetes profiling demos

Two demos that run Spark as real k8s pods so the gProfiler agent DaemonSet
profiles the executor JVMs per thread:

| demo | what runs | use it to see |
|------|-----------|---------------|
| **single** (`spark-demo`) | one CPU-burn app: 6 executors x 4 task threads | per-thread Java flamegraph of one busy Spark app |
| **multi** (`spark-multi-demo`) | 4 *different* apps side by side | **relative weight** of different workloads |

## Why "multi"? (relative weight)

When every executor runs the same kernel, all the per-thread flamegraphs look
alike. `spark-multi` submits four apps that each hammer a different hot path, so
the profile shows visibly different stacks and lets you compare where CPU goes:

| mode | app name | dominant frames |
|------|----------|-----------------|
| `agg`   | `spark-agg`   | `WholeStageCodegen` + transcendental math (`sin/cos/sqrt/log`) |
| `join`  | `spark-join`  | sort-merge join: `UnsafeExternalSorter`, `ShuffleWriter`, `Sorter` |
| `regex` | `spark-regex` | `java.util.regex` (`Pattern`/`Matcher`) + codegen |
| `pyudf` | `spark-pyudf` | Python UDF: JVM `PythonRunner` + Python worker CPU (`appid: pyspark`) |
| `skew`  | `spark-skew`  | data skew: ONE task-launch-worker thread dominates, the rest finish fast |

`agg/join/regex/pyudf` make the *apps* differ. `skew` makes the *threads within one
app* differ -- ~98% of rows land on one partition so a single "Executor task launch
worker" thread is far wider than its peers (vs the uniform widths you get when every
task does equal work).

**Preferred readable demo** (one app, few partitions, short profile):

```bash
# 4 partitions keep the per-thread forest small; skew makes one task ~3-4x wider.
make -f Makefile.k8s spark-multi \
  SPARK_MODES="skew" SPARK_PARTITIONS=4 SPARK_MULTI_SECONDS=500
make -f Makefile.k8s spark-profile SPARK_PROFILE_SECONDS=30
```

Measured on the sandbox (one 30s profile while skew was busy):

```
task 1:  53.7%   ################################   <- hot partition
task 3:  18.5%   ###########
task 2:  15.3%   #########
task 0:  12.5%   #######
```

`SPARK_PARTITIONS` (default 24) controls how many task-thread columns appear under
async-profiler's per-sample rename. Lower it when the flamegraph looks like a
forest of equal slivers.

Example from one 120s host profile (8 executor JVMs, 16-core node):

```
spark-pyudf   43.9% of Spark CPU     (Python worker dominated)
spark-regex   31.6%
spark-join    14.0%
spark-agg     10.4%
```

## Running

```bash
cd deploy/k8s-sandbox

make -f Makefile.k8s spark-demo         # single app, one-shot
make -f Makefile.k8s spark-multi-demo   # 4 distinct apps, one-shot

# granular
make -f Makefile.k8s spark-multi SPARK_MODES="agg join regex pyudf" SPARK_MULTI_SECONDS=1200
make -f Makefile.k8s spark-status
make -f Makefile.k8s spark-profile SPARK_PROFILE_SECONDS=120
make -f Makefile.k8s spark-clean
```

## Reading the per-thread flamegraph

The agent runs async-profiler in `threads` mode, so each stack is prefixed with its
JVM thread name. Spark task threads look like:

```
Executor task launch worker for task 1.0 in stage 165.0 (TID 1376) tid=334
                                    │    │          │            │        └ OS thread id
                                    │    │          │            └ Spark task id (unique within the app)
                                    │    │          └ stage id (within the app)
                                    └────┴ taskId.attempt
```

That identifies the task/stage/thread **within one JVM**, but NOT which app -- stage
and TID numbering restart per app. The app is a *separate* frame in every sample: the
executor pod, e.g. `k8s_spark_spark-<mode>-<execid>-exec-N_spark_...`. To attribute a
thread to an app:

- Switch the flamegraph's top grouping from `appid` to **container / process name**
  (or filter by pod). Then each thread rolls up under its `spark-<mode>` pod.
- Or, in the raw collapsed `.gz`, group by the `spark-<mode>-...-exec-N` frame.

Why they all share one `appid: java: org.apache.spark...KubernetesExecutorBackend`:
see gotcha #2 below. If you want the appid dropdown itself to separate the apps,
patch the agent's `_JavaSparkApplicationIdentifier` to also match the k8s executor
backend class (it already reads `spark.app.name`), then `make agent-build` + rollout.

## Files

- `spark_cpu_job.py` — single-app CPU burn (used by `spark-demo`).
- `spark_workloads.py` — multi-mode workloads (used by `spark-multi`), dispatched by `<mode>` arg.
- `Dockerfile` — thin layer over `apache/spark:3.5.1` baking both scripts in.
- `00-rbac.yaml` — `spark` namespace + ServiceAccount/Role so the driver can create executor pods.
- `10-submit-job.yaml` — single-app `spark-submit` Job (cluster mode).
- `11-submit-workload.yaml` — templated per-mode Job (`__SUFFIX__/__MODE__/__APPNAME__/__SECONDS__/__PARTS__`).

## Gotchas (learned the hard way)

1. **Profile while the apps are running.** The Spark Jobs exit after
   `SPARK_MULTI_SECONDS`. If they finish before the profile window, async-profiler
   has no JVMs to attach to and you get a Python-only capture. `spark-*-demo`
   size the run window to cover profiling; if you drive it manually, submit with a
   long duration and profile promptly (`spark-status` should show executors
   `Running`).
2. **appid does not split Spark apps on k8s 3.5.** All executors report
   `appid: java: org.apache.spark...KubernetesExecutorBackend`, so
   `--java-collect-spark-app-name-as-appid` won't separate them in the UI.
   gProfiler's Spark detector (`_JavaSparkApplicationIdentifier`) matches
   `org.apache.spark.executor` in argv, which the k8s executor backend main class
   no longer contains. Group by the executor **pod** (its name is a frame in every
   sample) or the `workload=<mode>` pod label instead.
3. **Uniform workloads + per-thread naming = a forest.** Spark renames the
   executor task thread for *every* task (`... for task X in stage Y [TID N]`),
   so a busy uniform app fans into one thin column per task. Use `skew` (or
   lower `SPARK_PARTITIONS`) when you want a readable per-thread view.
4. **Wedged ad-hoc agent.** If `spark-profile` returns success but no new `.gz`
   lands in S3 / the UI stays stale, the agent may be stuck re-skipping a prior
   command (`Command ID ... already received, skipping`). Restart it:
   `kubectl -n perf-studio rollout restart ds/gprofiler-agent`.
