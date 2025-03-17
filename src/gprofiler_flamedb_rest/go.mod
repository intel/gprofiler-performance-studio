module restflamedb

go 1.20

replace restflamedb/db => ./db

replace restflamedb/common => ./common

replace restflamedb/handlers => ./handlers

replace restflamedb/config => ./config

require (
	github.com/gin-contrib/cors v1.6.0
	github.com/gin-contrib/gzip v0.0.6
	github.com/gin-gonic/gin v1.9.1
	restflamedb/common v0.0.0-00010101000000-000000000000
	restflamedb/config v0.0.0-00010101000000-000000000000
	restflamedb/db v0.0.0-00010101000000-000000000000
	restflamedb/handlers v0.0.0-00010101000000-000000000000
)

require (
	github.com/ClickHouse/clickhouse-go v1.5.4 // indirect
	github.com/OneOfOne/xxhash v1.2.8 // indirect
	github.com/a8m/rql v1.3.0 // indirect
	github.com/bytedance/sonic v1.10.2 // indirect
	github.com/chenzhuoyu/base64x v0.0.0-20230717121745-296ad89f973d // indirect
	github.com/chenzhuoyu/iasm v0.9.1 // indirect
	github.com/cloudflare/golz4 v0.0.0-20150217214814-ef862a3cdc58 // indirect
	github.com/gabriel-vasile/mimetype v1.4.3 // indirect
	github.com/gin-contrib/sse v0.1.0 // indirect
	github.com/go-playground/locales v0.14.1 // indirect
	github.com/go-playground/universal-translator v0.18.1 // indirect
	github.com/go-playground/validator/v10 v10.17.0 // indirect
	github.com/goccy/go-json v0.10.2 // indirect
	github.com/josharian/intern v1.0.0 // indirect
	github.com/json-iterator/go v1.1.12 // indirect
	github.com/klauspost/cpuid/v2 v2.2.6 // indirect
	github.com/leodido/go-urn v1.2.4 // indirect
	github.com/mailru/easyjson v0.7.7 // indirect
	github.com/mattn/go-isatty v0.0.20 // indirect
	github.com/modern-go/concurrent v0.0.0-20180306012644-bacd9c7ef1dd // indirect
	github.com/modern-go/reflect2 v1.0.2 // indirect
	github.com/montanaflynn/stats v0.7.1 // indirect
	github.com/pelletier/go-toml/v2 v2.1.1 // indirect
	github.com/twitchyliquid64/golang-asm v0.15.1 // indirect
	github.com/ugorji/go/codec v1.2.12 // indirect
	golang.org/x/arch v0.6.0 // indirect
	golang.org/x/crypto v0.33.0 // indirect
	golang.org/x/net v0.33.0 // indirect
	golang.org/x/sys v0.15.0 // indirect
	golang.org/x/text v0.14.0 // indirect
	google.golang.org/protobuf v1.33.0 // indirect
	gopkg.in/yaml.v3 v3.0.1 // indirect
)
