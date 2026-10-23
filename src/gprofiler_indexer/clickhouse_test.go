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
	"context"
	"fmt"
	"os/exec"
	"sync"
	"testing"
	"time"
)

const (
	testClickhousePort = 19512
	testClickhouseVer  = "22.8"
)

func setupClickhouse(tb testing.TB) func(tb testing.TB) {
	logger.Debug("setupClickhouse setup")
	tearDown := func(tb testing.TB) {
		logger.Debug("setupClickhouse teardown")
		cmdStr := "docker rm -f indexer-test-ch-server"
		_, err := exec.Command("/bin/sh", "-c", cmdStr).Output()
		if err != nil {
			tb.Fatal(err)
		}
	}
	cmdStr := fmt.Sprintf("docker run -d -p %d:9000 --name indexer-test-ch-server clickhouse/clickhouse-server:%s",
		testClickhousePort, testClickhouseVer)
	_, err := exec.Command("/bin/sh", "-c", cmdStr).Output()
	if err != nil {
		tb.Fatal(err)
	}
	time.Sleep(3 * time.Second)

	cmdStr = "docker cp sql/create_ch_schema.sql indexer-test-ch-server:/ " +
		"&& docker exec indexer-test-ch-server bash -c \"cat /create_ch_schema.sql | clickhouse-client -mn\""
	out, err := exec.Command("/bin/sh", "-c", cmdStr).Output()
	if err != nil {
		tearDown(tb)
		tb.Fatal(string(out), err)
	}

	return tearDown
}

func ingestData(tb testing.TB, args *CLIArgs, filename string) {
	var tasksWaitGroup sync.WaitGroup
	var listenSQSWaitGroup sync.WaitGroup
	var buffWriterWaitGroup sync.WaitGroup

	channels := RecordChannels{
		StacksRecords:  make(chan StackRecord, args.ClickHouseStacksBatchSize),
		MetricsRecords: make(chan MetricRecord, args.ClickHouseMetricsBatchSize),
	}
	stopChannel := make(chan bool, 1)
	frameReplacer = NewFrameReplacer()
	err := frameReplacer.InitRegexps(args.FrameReplaceFileName)
	if err != nil {
		tb.Fatal(err)
	}
	callStackWriter := NewProfilesWriter(&channels)
	tasksWaitGroup.Add(1)

	tasks := make(chan SQSMessage, 1)
	go Worker(0, args, tasks, callStackWriter, &tasksWaitGroup)
	buffWriterWaitGroup.Add(1)
	go BufferedClickHouseWrite(args, &channels, &buffWriterWaitGroup)

	tasks <- SQSMessage{
		Filename: filename,
	}

	stopChannel <- true
	listenSQSWaitGroup.Wait()
	close(tasks)
	tasksWaitGroup.Wait()
	close(channels.StacksRecords)
	close(channels.MetricsRecords)
	buffWriterWaitGroup.Wait()
}

func TestDataIngestion(t *testing.T) {
	teardown := setupClickhouse(t)
	defer teardown(t)

	args := NewCliArgs()
	args.ClickHouseAddr = fmt.Sprintf("localhost:%d", testClickhousePort)

	ingestData(t, args, "testdata/test_stackfile")
	//	time.Sleep(300 * time.Second)
	// now test that the data was ingested
	settings := ClickHouseSettings{
		Addr: args.ClickHouseAddr,
	}
	chClient, _ := NewClickHouseClient(&settings)
	var rowCount uint64
	err := chClient.conn.QueryRow(context.Background(), "SELECT count() FROM flamedb.samples").Scan(&rowCount)
	if err != nil {
		t.Fatal(err)
	}
	if rowCount != 651 {
		t.Fatalf("wrong row count: %d", rowCount)
	}
}

func TestDataIngestionHTML(t *testing.T) {
	teardown := setupClickhouse(t)
	defer teardown(t)

	args := NewCliArgs()
	args.ClickHouseAddr = fmt.Sprintf("localhost:%d", testClickhousePort)

	ingestData(t, args, "testdata/test_stackfile_html")
	//	time.Sleep(300 * time.Second)
	// now test that the data was ingested
	settings := ClickHouseSettings{
		Addr: args.ClickHouseAddr,
	}
	chClient, _ := NewClickHouseClient(&settings)
	var rowCount uint64
	err := chClient.conn.QueryRow(context.Background(), "SELECT count() FROM flamedb.samples").Scan(&rowCount)
	if err != nil {
		t.Fatal(err)
	}
	if rowCount != 651 {
		t.Fatalf("wrong row count: %d", rowCount)
	}
	var path string
	chClient.conn.QueryRow(context.Background(), "SELECT HTMLPath FROM flamedb.metrics").Scan(&path)
	if path == "" {
		t.Fatalf("HTMLPath expected to be non empty")
	}
}

func TestDbColumnsMatchAttributes(t *testing.T) {
	for _, r := range []RecordsAttributesUnpack{StackRecord{}, MetricRecord{}} {
		if c, a := len(r.getDbColumns()), len(r.getDbAttributes()); c != a {
			t.Errorf("%T: %d columns but %d attributes", r, c, a)
		}
	}
}
