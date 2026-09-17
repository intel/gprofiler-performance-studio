-- Increase the id-sequence cache on the heartbeat inventory tables.
--
-- Every heartbeat re-proposes its full container/process inventory. The previous
-- INSERT ... ON CONFLICT evaluated the id DEFAULT (nextval) for every proposed row
-- BEFORE resolving the conflict, so ~all rows (unchanged, re-reported each beat)
-- still burned a sequence value. At fleet scale this was ~58k nextval/s on cache=1
-- sequences, making the sequence buffer lock (LWLock:SerialBuffer) a top contention
-- point once heartbeat writes ran in parallel.
--
-- The application fix (only inserting genuinely-new rows) removes most of that burn;
-- this larger cache is a complementary safety margin for the remaining real inserts
-- and the one-per-heartbeat HostHeartbeats upsert. Each backend now reserves a block
-- of ids per sequence-lock acquisition (~cache-factor fewer acquisitions). Gaps and
-- non-monotonic ids across sessions are harmless for these surrogate keys.
--
-- Safe to run online and idempotent (re-running just re-sets the same cache).

ALTER SEQUENCE heartbeatprocesses_id_seq  CACHE 500;
ALTER SEQUENCE heartbeatcontainers_id_seq CACHE 500;
ALTER SEQUENCE hostheartbeats_id_seq      CACHE 500;
