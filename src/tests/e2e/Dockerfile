# In-network acceptance/UI test runner for the e2e harness.
# Runs pytest (API acceptance) from inside the compose network, so it can reach
# Postgres/ClickHouse/webapp by service name without exposing host ports.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /work

# Kept minimal on purpose; extended with playwright in the UI phase.
RUN pip install --no-cache-dir \
    pytest==8.2.0 \
    requests==2.32.3 \
    psycopg2-binary==2.9.9

# Test sources are mounted or copied at run time.
COPY tests/e2e /work/tests/e2e

CMD ["pytest", "-q", "tests/e2e"]
