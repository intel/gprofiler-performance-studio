//
// Copyright (C) 2023 Intel Corporation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

package main

import (
	"flag"
	"log"
	"restflamedb/common"
	"restflamedb/config"
	"restflamedb/db"
	"restflamedb/handlers"

	"github.com/gin-contrib/cors"
	"github.com/gin-contrib/gzip"
	"github.com/gin-gonic/gin"
)

func main() {
	flag.StringVar(&config.ClickHouseAddr, "clickhouse-addr",
		common.LookupEnvOrDefault("CLICKHOUSE_ADDR", config.ClickHouseAddr),
		"ClickHouse address like 127.0.0.1:9000")
	flag.StringVar(&config.ClickHouseStacksTable, "clickhouse-stacks-table",
		common.LookupEnvOrDefault("CLICKHOUSE_STACKS_TABLE", config.ClickHouseStacksTable),
		"ClickHouse stacks table (default samples)")
	flag.StringVar(&config.ClickHouseMetricsTable, "clickhouse-metrics-table",
		common.LookupEnvOrDefault("CLICKHOUSE_METRICS_TABLE", config.ClickHouseMetricsTable),
		"ClickHouse metrics table (default metrics)")
	flag.StringVar(&config.ClickHouseMetricsExtTable, "clickhouse-metrics-ext-table",
		common.LookupEnvOrDefault("CLICKHOUSE_METRICS_EXT_TABLE", config.ClickHouseMetricsExtTable),
		"ClickHouse additional metrics table (default metrics_ext)")
	flag.BoolVar(&config.UseTLS, "use-tls",
		common.LookupEnvOrDefault("USE_TLS", config.UseTLS),
		"Run server with TLS ('false' or '0' to disable), (default true)")
	flag.StringVar(&config.CertFilePath, "cert-file-path",
		common.LookupEnvOrDefault("CERT_FILE_PATH", config.CertFilePath),
		"default empty")
	flag.StringVar(&config.KeyFilePath, "key-file-path",
		common.LookupEnvOrDefault("KEY_FILE_PATH", config.KeyFilePath),
		"default empty")
	flag.StringVar(&config.Credentials, "basic-auth-credentials",
		common.LookupEnvOrDefault("BASIC_AUTH_CREDENTIALS", config.Credentials),
		"Credentials to use in basic auth header")
	flag.IntVar(&config.RawRetentionDays, "raw-retention-days",
		common.LookupEnvOrDefault("RAW_RETENTION_DAYS", config.RawRetentionDays),
		"Raw data retention period in days")
	flag.IntVar(&config.MinuteRetentionDays, "minute-retention-days",
		common.LookupEnvOrDefault("MINUTE_RETENTION_DAYS", config.MinuteRetentionDays),
		"Minute aggregation retention period in days")
	flag.IntVar(&config.HourlyRetentionDays, "hourly-retention-days",
		common.LookupEnvOrDefault("HOURLY_RETENTION_DAYS", config.HourlyRetentionDays),
		"Hourly aggregation retention period in days")
	flag.IntVar(&config.DailyRetentionDays, "daily-retention-days",
		common.LookupEnvOrDefault("DAILY_RETENTION_DAYS", config.DailyRetentionDays),
		"Daily aggregation retention period in days")
	flag.Parse()

	h := handlers.Handlers{
		ChClient: db.NewClickHouseClient(config.ClickHouseAddr),
	}

	router := gin.Default()

	authorizedUsers, err := common.ParseCredentials(config.Credentials)
	if err != nil {
		log.Fatalf("Error parsing basic auth credentials: %v", err)
	}
	router.Use(gin.BasicAuth(authorizedUsers))

	cfg := cors.DefaultConfig()
	// Allow all origins
	cfg.AllowAllOrigins = true
	router.Use(cors.New(cfg))
	router.Use(gzip.Gzip(gzip.DefaultCompression))
	router.Use(handlers.StartTime())
	// Register endpoints
	router.GET("/api/v1/flamegraph", h.GetFlamegraph)
	router.GET("/api/v1/query", h.QueryMeta)
	router.GET("/api/v1/sessions_count", h.QuerySessionsCount)
	router.GET("/api/v1/services", h.QueryServices)
	router.GET("/api/v1/metrics/summary", h.GetMetricsSummary)
	router.POST("/api/v1/metrics/services_list_summary", h.GetMetricsServicesListSummary)
	router.GET("/api/v1/metrics/graph", h.GetMetricsGraph)
	router.GET("/api/v1/metrics/ext/names", h.GetMetricsExtNames)
	router.GET("/api/v1/metrics/ext/graph", h.GetMetricsExtGraph)
	router.GET("/api/v1/metrics/cpu_trend", h.GetMetricsCpuTrends)
	router.GET("/api/v1/metrics/lasthtml", h.GetLastHTML)
	if config.UseTLS {
		router.RunTLS("0.0.0.0:4433", config.CertFilePath, config.KeyFilePath)
	} else {
		router.Run("0.0.0.0:8080")
	}
}
