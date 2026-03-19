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
	"database/sql"
	"fmt"
	"time"

	_ "github.com/lib/pq"
	"github.com/lib/pq"
)

var db *sql.DB

// InitPostgres initializes the PostgreSQL connection pool
func InitPostgres(connStr string) error {
	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		return fmt.Errorf("failed to open postgres connection: %w", err)
	}

	// Test the connection
	err = db.Ping()
	if err != nil {
		return fmt.Errorf("failed to ping postgres: %w", err)
	}

	// Set connection pool settings for optimal performance
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	return nil
}

// StoreAdhocFlamegraphMetadata stores metadata for an adhoc flamegraph HTML file in PostgreSQL.
// This is called after successfully uploading the flamegraph HTML to S3.
func StoreAdhocFlamegraphMetadata(
	serviceId int,
	hostname string,
	s3Key string,
	perfEvents []string,
	timestamp time.Time,
	fileSize int64,
) error {
	if db == nil {
		return fmt.Errorf("postgres connection not initialized")
	}

	query := `
		INSERT INTO AdhocFlamegraphMetadata 
		(service_id, hostname, s3_key, perf_events, start_time, end_time, file_size)
		VALUES ($1, $2, $3, $4, $5, $5, $6)
		ON CONFLICT (s3_key) DO UPDATE SET
			perf_events = EXCLUDED.perf_events,
			file_size = EXCLUDED.file_size
	`

	_, err := db.Exec(
		query,
		serviceId,
		hostname,
		s3Key,
		pq.Array(perfEvents),
		timestamp,
		fileSize,
	)

	if err != nil {
		return fmt.Errorf("failed to insert flamegraph metadata: %w", err)
	}

	return nil
}

// ClosePostgres closes the PostgreSQL connection pool
func ClosePostgres() error {
	if db != nil {
		return db.Close()
	}
	return nil
}
