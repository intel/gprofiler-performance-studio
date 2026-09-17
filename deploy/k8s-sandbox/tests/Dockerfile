# In-cluster acceptance runner for the k8s sandbox.
#
# BUILD CONTEXT MUST BE THE STUDIO REPO ROOT (gprofiler-performance-studio/) so
# it can copy both the shared HTTP harness from the compose e2e suite and the
# k8s-specific tests:
#
#   docker build -f deploy/k8s-sandbox/tests/Dockerfile -t gprofiler-ps/k8s-tests:sandbox .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /work

RUN pip install --no-cache-dir \
    pytest==8.2.0 \
    requests==2.32.3

# Shared request/response harness (single source of truth with the compose suite).
COPY src/tests/e2e/harness.py /work/harness.py
# k8s-specific real-topology tests.
COPY deploy/k8s-sandbox/tests/conftest.py /work/conftest.py
COPY deploy/k8s-sandbox/tests/test_k8s_inventory.py /work/test_k8s_inventory.py

CMD ["pytest", "-q", "-rA", "test_k8s_inventory.py"]
