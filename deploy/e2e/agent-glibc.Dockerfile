# Wraps a locally-built gProfiler executable in a glibc base for the e2e harness.
#
# Build context MUST be the gprofiler agent repo root (so build/<arch>/gprofiler
# is present). Produce that exe first with the fast (no-staticx) build:
#
#   cd ../../gprofiler && scripts/build_x86_64_executable.sh --fast
#
# The --fast build skips staticx, so the exe is glibc-dynamic and needs a glibc
# base (ubuntu) rather than the alpine base in the repo's container.Dockerfile.
ARG ARCH=x86_64
FROM ubuntu:22.04

ARG ARCH
ENV GPROFILER_IN_CONTAINER=1

COPY build/${ARCH}/gprofiler /gprofiler
RUN chmod +x /gprofiler

ENTRYPOINT ["/gprofiler"]
