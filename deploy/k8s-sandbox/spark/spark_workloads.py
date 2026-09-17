"""Several DISTINCT CPU-heavy Spark workloads, each with its own Spark app name.

Why this exists: when every executor runs the same kernel, the per-thread
flamegraphs all look alike. Running a few *different* apps side by side gives
gProfiler visibly different stacks and lets you compare RELATIVE weight across
apps.

How to tell the apps apart in the profile: each app's executor pods are named
`spark-<mode>-<id>-exec-N` and that pod identity appears as a frame in every
sample (k8s_spark_spark-<mode>-...-exec-N_spark_...), so you group/filter by
workload there. NOTE: on Spark 3.5's k8s executors the built-in
--java-collect-spark-app-name-as-appid does NOT split the apps -- they all share
`appid: java: org.apache.spark...KubernetesExecutorBackend` (gProfiler's spark
detector keys off `org.apache.spark.executor` in argv, which the k8s executor
backend main class no longer matches). Group by the executor pod / the
`workload=<mode>` label instead. See spark/README.md.

Each mode stresses a different Catalyst/JVM path:
  agg    -> whole-stage codegen + transcendental math (HashAggregate, codegen)
  join   -> shuffle + sort-merge join (ExternalSorter, ShuffleWriter, SMJ)
  regex  -> string/regex parsing (java.util.regex, UTF8String)
  pyudf  -> Python UDF round-trips (JVM PythonRunner + socket, Python worker CPU)
  skew   -> deliberate data skew so ONE task thread dominates the flamegraph
            (the others finish fast) -- use it to see unequal per-thread weight

Usage: spark_workloads.py <mode> <run_seconds> [app_name]
"""
import math
import sys
import time

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

MODE = sys.argv[1] if len(sys.argv) > 1 else "agg"
RUN_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 300
APP_NAME = sys.argv[3] if len(sys.argv) > 3 else f"spark-{MODE}"
# Fewer partitions -> fewer tasks -> fewer per-thread columns in the flamegraph
# (each task becomes its own thread-name frame under per-sample renaming).
PARTITIONS = int(sys.argv[4]) if len(sys.argv) > 4 else 24

spark = SparkSession.builder.appName(APP_NAME).getOrCreate()
print(f">> {APP_NAME} starting: mode={MODE} run_seconds={RUN_SECONDS} "
      f"partitions={PARTITIONS}", flush=True)


def run_agg():
    """Transcendental math folded into whole-stage codegen -> pure JVM CPU."""
    rows = 20_000_000
    df = spark.range(0, rows, numPartitions=PARTITIONS)
    for _ in range(8):
        df = (df.withColumn("v", F.sqrt(F.col("id") + 1.0))
                .withColumn("v", F.sin(F.col("v")) * F.cos(F.col("v"))
                            + F.log(F.col("v") + 2.0))
                .withColumn("id", (F.col("id") + 1) % rows))
    return df.agg(F.expr("sum(v) as s")).collect()[0]["s"]


def run_join():
    """1:1 sort-merge join across two big frames -> heavy shuffle + external sort."""
    rows = 8_000_000
    left = (spark.range(0, rows, numPartitions=PARTITIONS)
            .withColumn("k", (F.col("id") * 2654435761) % rows)
            .withColumnRenamed("id", "lid"))
    right = (spark.range(0, rows, numPartitions=PARTITIONS)
             .withColumn("k", (F.col("id") * 40503) % rows)
             .withColumnRenamed("id", "rid"))
    joined = left.join(right, on="k", how="inner")
    return joined.agg(F.count(F.lit(1)).alias("c")).collect()[0]["c"]


def run_regex():
    """Regex extract/replace over synthetic strings -> java.util.regex hot path."""
    rows = 8_000_000
    base = spark.range(0, rows, numPartitions=PARTITIONS)
    s = base.withColumn(
        "s",
        F.concat(F.lit("id-"), F.col("id").cast("string"),
                 F.lit("-x9y8z7-"), (F.col("id") % 9973).cast("string")),
    )
    for _ in range(6):
        s = (s.withColumn("d", F.regexp_extract(F.col("s"), r"id-(\d+)-", 1))
               .withColumn("up", F.upper(F.col("s")))
               .withColumn("rep", F.regexp_replace(F.col("s"), r"[0-9]", "#")))
    return s.agg(F.sum(F.length(F.col("rep")))).collect()[0][0]


def run_pyudf():
    """Python UDF forces rows through Python workers -> distinct PythonRunner/
    socket stacks in the JVM (plus CPU burned in the python worker processes)."""
    rows = 1_500_000

    @F.udf(DoubleType())
    def churn(x):
        v = float(x)
        for _ in range(200):
            v = math.sin(v) * math.cos(v) + math.sqrt(abs(v) + 1.0)
        return v

    df = spark.range(0, rows, numPartitions=PARTITIONS).withColumn("v", churn(F.col("id")))
    return df.agg(F.sum("v")).collect()[0][0]


def run_skew():
    """DELIBERATE DATA SKEW: ~98% of rows collapse onto a single partition key, so
    after the repartition ONE downstream task gets almost all the rows and its
    'Executor task launch worker' thread dominates the flamegraph while the other
    task threads finish quickly. Use this to see one thread far wider than the rest
    (vs the uniform-width threads you get when every task does equal work)."""
    rows = 12_000_000
    base = spark.range(0, rows, numPartitions=PARTITIONS)
    # id % 50 != 0  -> key 0 (98% of rows); else a spread key. One hot partition.
    keyed = base.withColumn("p", F.when(F.col("id") % 50 != 0, F.lit(0)).otherwise(F.col("id")))
    skewed = keyed.repartition(PARTITIONS, "p")
    # Heavy per-row math in the skewed stage so the hot task actually burns CPU.
    for _ in range(6):
        skewed = (skewed.withColumn("v", F.sqrt(F.col("id") + 1.0))
                        .withColumn("v", F.sin(F.col("v")) * F.cos(F.col("v"))
                                    + F.log(F.col("v") + 2.0)))
    return skewed.agg(F.sum("v").alias("s")).collect()[0]["s"]


RUNNERS = {"agg": run_agg, "join": run_join, "regex": run_regex,
           "pyudf": run_pyudf, "skew": run_skew}
runner = RUNNERS.get(MODE, run_agg)

deadline = time.time() + RUN_SECONDS
iteration = 0
while time.time() < deadline:
    result = runner()
    iteration += 1
    print(f">> {APP_NAME} iter {iteration} result={result}", flush=True)

print(f">> {APP_NAME} finished", flush=True)
spark.stop()
