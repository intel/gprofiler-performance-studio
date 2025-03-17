module restflamedb/handlers

go 1.20

replace restflamedb/db => ../db

replace restflamedb/config => ../config

replace restflamedb/common => ../common

require (
	github.com/a8m/rql v1.3.0
	github.com/gin-gonic/gin v1.9.1
	restflamedb/common v0.0.0-00010101000000-000000000000
	restflamedb/db v0.0.0-00010101000000-000000000000
)

require (
	github.com/ClickHouse/clickhouse-go v1.5.1 // indirect
	github.com/OneOfOne/xxhash v1.2.8 // indirect
	github.com/cloudflare/golz4 v0.0.0-20150217214814-ef862a3cdc58 // indirect
	github.com/gin-contrib/sse v0.1.0 // indirect
	github.com/go-playground/locales v0.14.1 // indirect
	github.com/go-playground/universal-translator v0.18.1 // indirect
	github.com/go-playground/validator/v10 v10.14.0 // indirect
	github.com/josharian/intern v1.0.0 // indirect
	github.com/json-iterator/go v1.1.12 // indirect
	github.com/leodido/go-urn v1.2.4 // indirect
	github.com/mailru/easyjson v0.7.7 // indirect
	github.com/mattn/go-isatty v0.0.19 // indirect
	github.com/modern-go/concurrent v0.0.0-20180306012644-bacd9c7ef1dd // indirect
	github.com/modern-go/reflect2 v1.0.2 // indirect
	github.com/montanaflynn/stats v0.6.6 // indirect
	github.com/ugorji/go/codec v1.2.11 // indirect
	golang.org/x/crypto v0.33.0 // indirect
	golang.org/x/sys v0.15.0 // indirect
	golang.org/x/xerrors v0.0.0-20200804184101-5ec99f83aff1 // indirect
	google.golang.org/protobuf v1.30.0 // indirect
	restflamedb/config v0.0.0-00010101000000-000000000000 // indirect
)
