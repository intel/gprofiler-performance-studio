# Playwright UI acceptance tests

Drives the profiling console through the internal nginx (basic auth +
self-signed TLS) and asserts the start/stop confirmation flow (dry-run
validation + submit). The STOP case is the UI regression test for the
host-level-stop bug.

Runs in the official Playwright browser image on the compose network — don't run
it against the host (host browser libs may be missing). Use the e2e harness:

```bash
cd ../../../deploy
make -f Makefile.e2e e2e-up        # or e2e-up-src (source-built agent)
make -f Makefile.e2e e2e-ui-test   # builds this runner and executes it in-network
```

Full harness docs (topology, LocalStack S3/SQS, portability):
[`deploy/E2E_HARNESS.md`](../../../deploy/E2E_HARNESS.md).
