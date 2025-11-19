# FlameDB ClickHouse Cluster Schema Documentation

## Overview

FlameDB uses a distributed ClickHouse cluster architecture to store and analyze profiling data at scale. The schema implements a tiered storage approach with multiple aggregation levels to optimize both storage efficiency and query performance.

## Architecture Components

### 1. ClickHouse Cluster Setup

The system runs on a **ClickHouse cluster** consisting of multiple nodes:
- **Sharding**: Data is distributed across nodes using hash-based partitioning
- **Replication**: Each shard is replicated for high availability
- **Distributed Tables**: Virtual tables that route queries across all cluster nodes

### 2. Table Architecture Pattern

Each data type follows a consistent 3-layer pattern:

```
┌─────────────────────┐
│ Distributed Table   │  ← Virtual table (routes queries)
│ (flamedb.samples)   │
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│ Local Tables        │  ← Physical tables (store actual data)
│ (samples_local)     │
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│ Materialized Views  │  ← Auto-aggregation (where applicable)
│ (samples_1hour_mv)  │
└─────────────────────┘
```

## Schema Tables

### Raw Data Storage

#### `flamedb.samples` (Distributed) → `flamedb.samples_local` (Physical)
- **Purpose**: Stores raw profiling stack traces
- **Partitioning**: By date (`toYYYYMMDD(Timestamp)`)
- **Sharding Key**: `CallStackHash`
- **Retention**: 7 days (configurable)
- **Columns**:
  - `Timestamp`: When the sample was collected
  - `ServiceId`: Application/service identifier
  - `HostName`, `ContainerName`: Runtime environment
  - `CallStackHash`, `CallStackName`, `CallStackParent`: Stack trace data
  - `NumSamples`: Sample count

#### `flamedb.metrics` (Distributed) → `flamedb.metrics_local` (Physical)
- **Purpose**: Stores CPU and memory metrics per host
- **Sharding Key**: `ServiceId`
- **Retention**: 90 days (recommended)
- **Columns**:
  - `CPUAverageUsedPercent`, `MemoryAverageUsedPercent`: Resource usage
  - `HostName`, `InstanceType`: Host information

### Aggregated Data (Materialized Views)

The schema creates multiple aggregation levels to optimize query performance:

#### 1-Minute Aggregation
- **Table**: `flamedb.samples_1min` → `flamedb.samples_1min_local`
- **Purpose**: Time-series charts and recent analysis
- **Aggregation**: Root stack frames only (`CallStackParent = 0`)
- **Retention**: 30 days (recommended)

#### 1-Hour Aggregation
- **Tables**: 
  - `flamedb.samples_1hour` → `flamedb.samples_1hour_local_store`
  - `flamedb.samples_1hour_all` → `flamedb.samples_1hour_all_local_store`
- **Purpose**: Medium-term trend analysis
- **Variants**:
  - `samples_1hour`: Maintains host/container breakdown
  - `samples_1hour_all`: Aggregates across all hosts/containers
- **Retention**: 90 days (recommended)

#### 1-Day Aggregation
- **Tables**:
  - `flamedb.samples_1day` → `flamedb.samples_1day_local_store`
  - `flamedb.samples_1day_all` → `flamedb.samples_1day_all_local_store`
- **Purpose**: Long-term historical analysis
- **Variants**: Same as 1-hour (with/without host breakdown)
- **Retention**: 365 days (recommended)

## Data Flow and Materialized Views

### How Materialized Views Work

**Materialized Views** in ClickHouse act as **real-time data transformation pipelines** that automatically aggregate data from `samples_local` whenever new data is inserted. They provide:

- **Immediate execution**: Views trigger on every INSERT to `samples_local`
- **Atomic operations**: Each INSERT processes all views in the same transaction
- **Automatic aggregation**: No batch processing delays - aggregation happens instantly

### Data Propagation Flow

```
┌─────────────────┐
│  samples_local  │ ← Raw profiling data inserted here
│  (Raw Storage)  │   (CallStacks, NumSamples, Timestamps, etc.)
└─────────┬───────┘
          │
          │ Every INSERT triggers ALL materialized views simultaneously
          │
          ├─────────────────────────────────────────────────────────────┐
          │                                                             │
          ▼                                                             ▼
┌─────────────────┐                                           ┌─────────────────┐
│samples_1min_mv  │                                           │samples_1hour_all│
│                 │                                           │     _local      │
│ SELECT          │                                           │                 │
│ toStartOfMinute │                                           │ SELECT          │
│ sum(NumSamples) │                                           │ toStartOfHour   │
│ WHERE Parent=0  │                                           │ sum(NumSamples) │
│ GROUP BY...     │                                           │ GROUP BY...     │
└─────────┬───────┘                                           └─────────┬───────┘
          │                                                             │
          ▼                                                             ▼
┌─────────────────┐                                           ┌─────────────────┐
│samples_1min     │                                           │samples_1hour_all│
│   _local        │                                           │ _local_store    │
│ (30-day TTL)    │                                           │ (90-day TTL)    │
└─────────────────┘                                           └─────────────────┘
          
          ├─────────────────────────────────────────────────────────────┐
          │                                                             │
          ▼                                                             ▼
┌─────────────────┐                                           ┌─────────────────┐
│samples_1hour    │                                           │samples_1day_all │
│    _local       │                                           │     _local      │
│                 │                                           │                 │
│ SELECT          │                                           │ SELECT          │
│ toStartOfHour   │                                           │ toStartOfDay    │
│ sum(NumSamples) │                                           │ sum(NumSamples) │
│ GROUP BY Host.. │                                           │ GROUP BY...     │
└─────────┬───────┘                                           └─────────┬───────┘
          │                                                             │
          ▼                                                             ▼
┌─────────────────┐                                           ┌─────────────────┐
│samples_1hour    │                                           │samples_1day_all │
│ _local_store    │                                           │ _local_store    │
│ (90-day TTL)    │                                           │ (365-day TTL)   │
└─────────────────┘                                           └─────────────────┘

          │
          ▼
┌─────────────────┐
│samples_1day     │
│    _local       │
│                 │
│ SELECT          │
│ toStartOfDay    │
│ sum(NumSamples) │
│ GROUP BY Host.. │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│samples_1day     │
│ _local_store    │
│ (365-day TTL)   │
└─────────────────┘
```

### Materialized View Details

#### 1. **1-Minute Aggregation** (`samples_1min_mv`)
- **Purpose**: Time-series charts and recent analysis
- **Filter**: Root stack frames only (`WHERE CallStackParent = 0`)
- **Aggregation**: Groups by service, host, container per minute
- **Storage**: `SummingMergeTree` engine automatically merges duplicate rows

#### 2. **1-Hour Aggregations**
- **Per-Host** (`samples_1hour_local`): Maintains host/container breakdown
- **All-Hosts** (`samples_1hour_all_local`): Aggregates across all infrastructure
- **Aggregation**: Groups by service, call stack, time bucket
- **Use Case**: Medium-term trend analysis

#### 3. **1-Day Aggregations**  
- **Per-Host** (`samples_1day_local`): Maintains host/container breakdown
- **All-Hosts** (`samples_1day_all_local`): Aggregates across all infrastructure
- **Aggregation**: Groups by service, call stack, daily buckets
- **Use Case**: Long-term historical analysis

### Key Aggregation Functions

```sql
-- Time bucketing
toStartOfMinute(Timestamp)  -- Rounds to minute boundary
toStartOfHour(Timestamp)    -- Rounds to hour boundary  
toStartOfDay(Timestamp)     -- Rounds to day boundary

-- Sample aggregation
sum(NumSamples)             -- Combines sample counts
sum(ErrNumSamples)          -- Combines error counts

-- Metadata preservation
any(CallStackName)          -- Keeps representative value
anyLast(InsertionTimestamp) -- Keeps latest insertion time
```

### Example Materialized View SQL

#### 1-Minute Aggregation (Root Frames Only)
```sql
CREATE MATERIALIZED VIEW flamedb.samples_1min_mv TO flamedb.samples_1min_local
AS SELECT 
    toStartOfMinute(Timestamp) AS Timestamp,
    ServiceId,
    InstanceType,
    ContainerEnvName,
    HostName,
    ContainerName,
    sum(NumSamples) AS NumSamples,
    HostNameHash,
    ContainerNameHash,
    anyLast(InsertionTimestamp) as InsertionTimestamp
FROM flamedb.samples_local 
WHERE CallStackParent = 0  -- Only root stack frames for time-series
GROUP BY ServiceId, InstanceType, ContainerEnvName, HostName, ContainerName, 
         HostNameHash, ContainerNameHash, Timestamp;
```

#### 1-Hour Aggregation (All Hosts Combined)
```sql
CREATE MATERIALIZED VIEW flamedb.samples_1hour_all_local TO flamedb.samples_1hour_all_local_store
AS SELECT 
    toStartOfHour(Timestamp) AS Timestamp,
    ServiceId,
    CallStackHash,
    any(CallStackName) as CallStackName,
    any(CallStackParent) as CallStackParent,
    sum(NumSamples) as NumSamples,
    sum(ErrNumSamples) as ErrNumSamples,
    anyLast(InsertionTimestamp) as InsertionTimestamp
FROM flamedb.samples_local
GROUP BY ServiceId, CallStackHash, Timestamp;
```

### Storage Efficiency Benefits

The materialized view architecture provides significant storage optimization:

- **Raw data** (`samples_local`): ~95% of storage, 7-day retention
- **1-minute aggregated**: ~3% of storage, 30-day retention  
- **1-hour aggregated**: ~1.5% of storage, 90-day retention
- **1-day aggregated**: ~0.5% of storage, 365-day retention

**Total storage reduction**: ~95% while maintaining full query capabilities across different time ranges and granularities.

### Real-time Processing Guarantees

1. **Atomicity**: All materialized views process within the same transaction as the original INSERT
2. **Consistency**: No data loss or partial aggregation states
3. **Immediate availability**: Aggregated data is queryable instantly after INSERT completes
4. **Automatic deduplication**: `SummingMergeTree` engine handles duplicate entries by summing `NumSamples`

## Query Routing Logic

The FlameDB REST API intelligently selects tables based on time range and resolution:

### Table Selection Rules
- **Raw data** (`samples`): Recent detailed queries (< 1 hour or when `resolution=raw`)
- **1-hour aggregation** (`samples_1hour`): Medium-term queries (1-24 hours)
- **1-day aggregation** (`samples_1day`): Long-term queries (> 24 hours)
- **Historical** (`samples_1day_all`): Very old data (> 14 days retention period)

### Multi-Range Queries
For queries spanning multiple time periods, the API splits requests:
```
24-hour query example:
├─→ First hour: Use raw data (samples)
├─→ Middle 22 hours: Use 1-hour aggregation (samples_1hour) 
└─→ Last hour: Use raw data (samples)
```

## TTL (Time To Live) Strategy

### Recommended Retention Policies

```sql
-- Raw data: High volume, short retention
ALTER TABLE flamedb.samples_local ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 7 DAY;

-- 1-minute aggregation: Medium volume, medium retention
ALTER TABLE flamedb.samples_1min_local ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 30 DAY;

-- 1-hour aggregations: Lower volume, longer retention
ALTER TABLE flamedb.samples_1hour_local_store ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 90 DAY;
ALTER TABLE flamedb.samples_1hour_all_local_store ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 90 DAY;

-- 1-day aggregations: Lowest volume, longest retention
ALTER TABLE flamedb.samples_1day_local_store ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 365 DAY;
ALTER TABLE flamedb.samples_1day_all_local_store ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 365 DAY;

-- Metrics: Resource usage trends
ALTER TABLE flamedb.metrics_local ON CLUSTER '{cluster}' 
MODIFY TTL Timestamp + INTERVAL 90 DAY;

-- Optional: Add TTL for deletion of old partitions (more aggressive cleanup)
-- This will delete entire partitions when they expire, which is more efficient
-- ALTER TABLE flamedb.samples_local ON CLUSTER '{cluster}' MODIFY TTL Timestamp + INTERVAL 7 DAY DELETE;
```

### Storage Efficiency Benefits
- **Raw data**: ~95% of storage, 7-day retention
- **1-hour aggregated**: ~4% of storage, 90-day retention  
- **1-day aggregated**: ~1% of storage, 365-day retention

This provides:
- Detailed recent analysis (7 days of raw data)
- Medium-term trends (90 days of hourly data)
- Long-term historical analysis (1 year of daily data)

## Cluster Configuration

### Replication
Tables use `ReplicatedMergeTree` engine:
```sql
ENGINE = ReplicatedMergeTree(
  '/clickhouse/{installation}/{cluster}/tables/{shard}/{database}/{table}',
  '{replica}'
)
```

### Sharding
Data distribution across cluster nodes:
- **samples**: Sharded by `CallStackHash` (evenly distributes stack traces)
- **metrics**: Sharded by `ServiceId` (groups service metrics together)

### Partitioning
All tables are partitioned by date (`toYYYYMMDD(Timestamp)`) for:
- Efficient TTL deletion (drops entire partitions)
- Improved query performance (partition pruning)
- Parallel processing across time ranges

## Usage Examples

### Querying Recent Data (< 1 hour)
```sql
-- Uses raw data automatically
SELECT CallStackName, sum(NumSamples) 
FROM flamedb.samples 
WHERE ServiceId = 123 
  AND Timestamp >= now() - INTERVAL 30 MINUTE
GROUP BY CallStackName;
```

### Querying Historical Trends (> 1 day)
```sql  
-- Uses 1-day aggregation automatically
SELECT toDate(Timestamp), sum(NumSamples)
FROM flamedb.samples_1day
WHERE ServiceId = 123
  AND Timestamp >= now() - INTERVAL 30 DAY
GROUP BY toDate(Timestamp);
```

### Checking Data Retention
```sql
-- Check oldest available data
SELECT min(Timestamp) as oldest_data FROM flamedb.samples;

-- Check TTL configuration
SELECT database, table, ttl_expression 
FROM system.table_ttl_info 
WHERE database = 'flamedb';
```

## Troubleshooting

### Missing Historical Data
If data older than 7 days is missing from `flamedb.samples`:
1. **Check TTL settings**: Raw data has 7-day retention by default
2. **Use aggregated tables**: Query `samples_1hour` or `samples_1day` for older data
3. **Verify cluster health**: Ensure all nodes are operational

### Query Performance
- **Recent data**: Query `samples` (distributed table)
- **Medium-term analysis**: Query `samples_1hour` 
- **Long-term trends**: Query `samples_1day`
- **Cross-host analysis**: Use `_all` variants for pre-aggregated data

### Storage Monitoring
```sql
-- Check table sizes
SELECT 
    database, table, 
    sum(bytes_on_disk) as size_bytes,
    count(*) as partitions
FROM system.parts 
WHERE database = 'flamedb' AND active = 1
GROUP BY database, table
ORDER BY size_bytes DESC;
```

## Best Practices

1. **Use appropriate aggregation level** for your query time range
2. **Apply TTL to local tables only** (not distributed tables)
3. **Monitor storage usage** and adjust retention as needed  
4. **Partition by date** for efficient TTL and query performance
5. **Shard by high-cardinality fields** for even distribution
