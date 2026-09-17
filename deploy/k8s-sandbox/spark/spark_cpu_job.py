"""CPU-heavy Spark job whose hot path stays inside the executor JVMs.

It uses only Catalyst/DataFrame built-ins (no Python UDFs), so all the arithmetic
runs as whole-stage-codegen'd bytecode on the executor JVM task threads -- exactly
the Java threads we want gProfiler to profile. The Python driver just orchestrates.

Arg 1 (optional): how many seconds to keep the cluster busy (default 300).
"""
import sys
import time

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sqrt, sin, cos, log, expr

RUN_SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
# 48 partitions keeps all executor task threads (6 execs x 4 cores = 24 slots)
# saturated with a backlog, so every JVM worker thread stays busy.
PARTITIONS = 48
ROWS = 40_000_000

spark = (
    SparkSession.builder.appName("spark-cpu-burn")
    .getOrCreate()
)
print(f">> spark-cpu-burn starting: run_seconds={RUN_SECONDS} "
      f"partitions={PARTITIONS} rows={ROWS}", flush=True)

deadline = time.time() + RUN_SECONDS
iteration = 0
while time.time() < deadline:
    df = spark.range(0, ROWS, numPartitions=PARTITIONS)
    # Stack several transcendental ops so each row costs real CPU in the JVM.
    for _ in range(8):
        df = (
            df.withColumn("v", sqrt(col("id") + 1.0))
              .withColumn("v", sin(col("v")) * cos(col("v")) + log(col("v") + 2.0))
              .withColumn("id", (col("id") + 1) % ROWS)
        )
    total = df.agg(expr("sum(v) as s")).collect()[0]["s"]
    iteration += 1
    print(f">> iteration {iteration} done sum={total}", flush=True)

print(">> spark-cpu-burn finished", flush=True)
spark.stop()
