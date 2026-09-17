# API acceptance tests (AT-S1 .. AT-S15)

In-network pytest suite that drives the **live** studio stack over HTTP and
codifies the workload-level profiling acceptance criteria from
[`heartbeat_doc/WORKLOAD_LEVEL_PROFILING_SPEC.md`](../../../heartbeat_doc/WORKLOAD_LEVEL_PROFILING_SPEC.md).

Do not run these directly — they need the full stack up. Use the e2e harness:

```bash
cd ../../../deploy
make -f Makefile.e2e e2e-up        # or e2e-up-src (source-built agent)
make -f Makefile.e2e e2e-test      # builds this runner and executes it in-network
```

Full harness docs (topology, LocalStack S3/SQS, portability):
[`deploy/E2E_HARNESS.md`](../../../deploy/E2E_HARNESS.md).
