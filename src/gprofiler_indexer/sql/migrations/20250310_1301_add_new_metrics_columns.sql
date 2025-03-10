ALTER TABLE flamedb.metrics
ADD COLUMN CPUFrequency Nullable (Float64) AFTER MemoryAverageUsedPercent;

ALTER TABLE flamedb.metrics
ADD COLUMN CPUCPI Nullable (Float64) AFTER CPUFrequency;

ALTER TABLE flamedb.metrics
ADD COLUMN CPUTMAFrontEndBound Nullable (Float64) AFTER CPUCPI;

ALTER TABLE flamedb.metrics
ADD COLUMN CPUTMABackendBound Nullable (Float64) AFTER CPUTMAFrontEndBound;

ALTER TABLE flamedb.metrics
ADD COLUMN CPUTMABadSpec Nullable (Float64) AFTER CPUTMABackendBound;

ALTER TABLE flamedb.metrics
ADD COLUMN CPUTMARetiring Nullable (Float64) AFTER CPUTMABadSpec;
