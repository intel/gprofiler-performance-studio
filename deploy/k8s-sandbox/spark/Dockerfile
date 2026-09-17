# Thin layer over the official Spark image that bakes in the CPU-burn job so the
# driver/executor pods can reference it via local:// (no file upload needed).
FROM apache/spark:3.5.1

COPY spark_cpu_job.py /opt/spark_cpu_job.py
COPY spark_workloads.py /opt/spark_workloads.py
