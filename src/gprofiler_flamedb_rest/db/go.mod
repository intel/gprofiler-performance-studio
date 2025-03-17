module restflamedb/db

go 1.20

replace restflamedb/common => ../common

replace restflamedb/config => ../config

require (
	github.com/ClickHouse/clickhouse-go v1.5.1
	github.com/montanaflynn/stats v0.6.6
	restflamedb/common v0.0.0-00010101000000-000000000000
	restflamedb/config v0.0.0-00010101000000-000000000000
)

require (
	github.com/OneOfOne/xxhash v1.2.8 // indirect
	github.com/cloudflare/golz4 v0.0.0-20150217214814-ef862a3cdc58 // indirect
)
