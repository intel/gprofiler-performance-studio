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

package db

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log"
	"math"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/ClickHouse/clickhouse-go"

	"restflamedb/common"
	"restflamedb/config"
)

const (
	operationName = "clickhouse"
	month         = time.Hour * 24 * 30
	halfHour      = time.Minute * 30
	hour          = time.Hour * 1
	day           = time.Hour * 24
	week          = time.Hour * 24 * 7
	twoWeeks      = time.Hour * 24 * 7 * 2
)

var (
	suffixesToTruncate = regexp.MustCompile(
		"_\\[j\\]$|_\\[j\\]_\\[s\\]$|_\\[i\\]$|_\\[i\\]_\\[s\\]$|_\\[0\\]$|_\\[0\\]_\\[s\\]$|_\\[1\\]$|_\\[1\\]_\\[s" +
			"\\]$|_\\[p\\]$|_\\[pe\\]$|_\\[k\\]$|_\\[php\\]$|_\\[pn\\]$|_\\[rb\\]$|_\\[net\\]$")
	Intervals = []time.Duration{
		halfHour,
		hour,
		day,
		week,
		twoWeeks,
		month,
	}
	IntervalsMapping = map[time.Duration]string{
		halfHour: "15 second",
		hour:     "30 second",
		day:      "15 minute",
		week:     "2 hour",
		twoWeeks: "6 hour",
		month:    "24 hour",
	}
	tableMapping = map[string]string{
		"hour": "1hour",
		"day":  "1day",
		"raw":  "raw",
	}
	queryFields = map[string]struct{}{
		"ContainerName":    {},
		"HostName":         {},
		"InstanceType":     {},
		"ContainerEnvName": {},
	}
)

type ClickHouseClient struct {
	client *sql.DB
}

type Sample struct {
	Time    time.Time `json:"time"`
	Samples int       `json:"samples"`
}

type TimeRange struct {
	Start     string
	End       string
	StartTime time.Time
}

type Frame struct {
	Hash         uint64
	ParentHash   uint64
	Name         string
	Suffix       string
	Samples      int
	IsRoot       bool
	Childrens    map[uint64]bool
	Lang         string
	SpecialType  string
	IsThirdParty string
	Insight      string
}

func convertNumToZeroIfNotValid(num float64) float64 {
	if math.IsNaN(num) {
		num = 0
	}
	return num
}

func (f *Frame) getTruncatedNameAndSuffix() (string, string) {
	if f.Lang == Cpp || f.Lang == NodeJS || f.Lang == Go {
		return f.Name, ""
	}
	suffix := suffixesToTruncate.FindString(f.Name)
	truncatedName := strings.TrimSuffix(f.Name, suffix)
	return truncatedName, suffix
}

func makeTimeRange(start time.Time, end time.Time) TimeRange {
	return TimeRange{Start: common.FormatTime(start), End: common.FormatTime(end), StartTime: start}
}

func makeStartOfHour(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), 0, 0, 0, t.Location())
}

func makeStartOfDay(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), 0, 0, 0, 0, t.Location())
}

func makeEndOfHour(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), 59, 59, 999, t.Location())
}

func makeEndOfDay(t time.Time) time.Time {
	return time.Date(t.Year(), t.Month(), t.Day(), 23, 59, 59, 999, t.Location())
}

func trimEndTime(end time.Time) time.Time {
	now := time.Now().UTC()
	diff := now.Sub(end)
	// check if endTime in query is less than 5 minutes ago, and adjust endTime
	// to prevent glitches due query from distributed table
	if diff < common.BackRewindTime {
		rewind := common.BackRewindTime - diff
		end = end.Add(-rewind)
	}
	return end
}

func sliceMultiRange(result map[string][]TimeRange, start time.Time, end time.Time) {
	end = trimEndTime(end)
	endOfHour := makeEndOfHour(start)
	endOfDay := makeEndOfDay(start)
	startOfDay := makeStartOfDay(end)
	startOfHour := makeStartOfHour(end)
	previousDay := makeEndOfDay(end.Add(-time.Hour * 24))
	previousHour := makeEndOfHour(end.Add(-time.Hour * 1))

	result["raw"] = append(result["raw"], makeTimeRange(start, endOfHour))
	result["raw"] = append(result["raw"], makeTimeRange(startOfHour, end))
	if end.After(endOfDay) {
		result["1hour"] = append(result["1hour"], makeTimeRange(endOfHour, endOfDay))
		if !previousDay.Equal(endOfDay) {
			result["1day"] = append(result["1day"], makeTimeRange(endOfDay, previousDay))
		}
		result["1hour"] = append(result["1hour"], makeTimeRange(startOfDay, previousHour))
	} else {
		result["1hour"] = append(result["1hour"], makeTimeRange(endOfHour, previousHour))
	}
}

func getInterval(startTime time.Time, endTime time.Time, interval string) string {
	if len(interval) > 0 {
		return interval
	}
	receivedTimeRangeDiff := endTime.Sub(startTime)
	intervalDiff := receivedTimeRangeDiff
	for index, intervalKey := range Intervals {
		if index == 0 && receivedTimeRangeDiff <= intervalKey {
			//smaller than the first interval (30 minutes)
			intervalDiff = intervalKey
			break
		}
		if index == len(Intervals)-1 && receivedTimeRangeDiff > intervalKey {
			//bigger than the last interval (1 month)
			intervalDiff = intervalKey
			break
		}
		if index > 0 && receivedTimeRangeDiff <= intervalKey && receivedTimeRangeDiff > Intervals[index-1] {
			//between any 2 intervals that are not the first and the last
			intervalDiff = intervalKey
			break
		}
	}
	interval, ok := IntervalsMapping[intervalDiff]
	if !ok {
		interval = "1 hour"
	}
	return interval
}

func GetTimeRanges(start time.Time, end time.Time, resolution string) map[string][]TimeRange {
	result := map[string][]TimeRange{
		"raw":             make([]TimeRange, 0),
		"1hour":           make([]TimeRange, 0),
		"1day":            make([]TimeRange, 0),
		"1day_historical": make([]TimeRange, 0),
	}

	delta := end.Sub(start)
	fullRange := makeTimeRange(start, trimEndTime(end))
	now := time.Now().UTC()

	// Retention thresholds from configurable settings
	rawRetentionInterval := time.Hour * 24 * time.Duration(config.RawRetentionDays)       // Raw data TTL
	hourlyRetentionInterval := time.Hour * 24 * time.Duration(config.HourlyRetentionDays) // Hourly data TTL
	dailyThreshold := time.Hour * 24 * time.Duration(config.HourlyRetentionDays)          // Switch to daily aggregation

	// Debug logging for table selection
	dataAge := now.Sub(start)
	log.Printf("📊 Table Selection: range=%v, delta=%v, age=%v, resolution=%s",
		start.Format("2006-01-02"), delta, dataAge, resolution)

	// For very old data (>90 days), use daily aggregation with day boundaries
	if now.Sub(start) >= dailyThreshold {
		result["1day_historical"] = append(result["1day_historical"], makeTimeRange(makeStartOfDay(start), makeEndOfDay(end)))
		return result
	}

	// For 7-90 day old data, raw is expired but hourly is available
	if now.Sub(start) >= rawRetentionInterval && now.Sub(start) < hourlyRetentionInterval {
		switch resolution {
		case "hour", "day":
			// Keep requested resolution for older data
			result[tableMapping[resolution]] = append(result[tableMapping[resolution]], fullRange)
			return result
		case "raw":
			// Force raw requests to use hourly when raw data is expired
			result["1hour"] = append(result["1hour"], fullRange)
			return result
		case "multi":
			if delta.Seconds() > time.Hour.Seconds() {
				// For multi-hour ranges, use sliceMultiRange but replace raw with hourly
				sliceMultiRange(result, start, end)
				// Move any raw ranges to hourly since raw data is expired
				if len(result["raw"]) > 0 {
					result["1hour"] = append(result["1hour"], result["raw"]...)
					result["raw"] = make([]TimeRange, 0)
				}
			} else {
				// For single-hour ranges, use hourly directly
				result["1hour"] = append(result["1hour"], fullRange)
			}
			return result
		}
	}

	switch resolution {
	case "hour", "day", "raw":
		result[tableMapping[resolution]] = append(
			result[tableMapping[resolution]], fullRange)
		return result
	case "multi":
		if delta.Seconds() > time.Hour.Seconds() {
			sliceMultiRange(result, start, end)
		} else {
			result["raw"] = append(result["raw"], fullRange)
		}
	}

	// Log final table selection
	log.Printf("📋 Final table selection:")
	for table, ranges := range result {
		if len(ranges) > 0 {
			log.Printf("  %s: %d ranges", table, len(ranges))
		}
	}

	return result
}

func BuildConditions(ContainerName []string, HostName []string, InstanceType []string, K8SObject []string,
	filterQuery common.QueryFilter) (string, common.QueryFilter) {
	if filterQuery.Clause != "" {
		return "", filterQuery
	}
	conditions := common.QueryFilter{}
	tablePrefix := "_all"

	if len(ContainerName) > 0 {
		containerNamesHash := make([]uint32, 0, len(ContainerName))
		for _, singleContainerName := range ContainerName {
			containerNamesHash = append(containerNamesHash, common.GetHash32AsInt(singleContainerName))
		}
		conditions.Clause += " AND (ContainerNameHash IN (@container_names))"
		conditions.Args = append(conditions.Args, sql.Named("container_names", containerNamesHash))
		tablePrefix = ""
	}
	if len(HostName) > 0 {
		hostNamesHash := make([]uint32, 0, len(HostName))
		for _, singleHostName := range HostName {
			hostNamesHash = append(hostNamesHash, common.GetHash32AsInt(singleHostName))
		}
		conditions.Clause += " AND (HostNameHash IN (@host_names))"
		conditions.Args = append(conditions.Args, sql.Named("host_names", hostNamesHash))
		tablePrefix = ""
	}
	if len(InstanceType) > 0 {
		tablePrefix = ""
		conditions.Clause += " AND (InstanceType IN (@instance_types))"
		conditions.Args = append(conditions.Args, sql.Named("instance_types", InstanceType))
	}
	if len(K8SObject) > 0 {
		tablePrefix = ""
		conditions.Clause += " AND (ContainerEnvName IN (@k8s_objects))"
		conditions.Args = append(conditions.Args, sql.Named("k8s_objects", K8SObject))
	}
	return tablePrefix, conditions
}

func withFilterArgs(filterQuery common.QueryFilter, args ...any) []any {
	queryArgs := make([]any, 0, len(filterQuery.Args)+len(args))
	queryArgs = append(queryArgs, filterQuery.Args...)
	return append(queryArgs, args...)
}

func NewClickHouseClient(addr string) *ClickHouseClient {
	db, err := sql.Open("clickhouse", "tcp://"+addr)
	if err != nil {
		log.Fatal(err)
	}
	if err := db.Ping(); err != nil {
		if exception, ok := err.(*clickhouse.Exception); ok {
			fmt.Printf("[%d] %s \n%s\n", exception.Code, exception.Message, exception.StackTrace)
		} else {
			fmt.Println(err)
		}
		log.Fatalf("ping failed")
		return nil
	}
	return &ClickHouseClient{
		client: db,
	}
}

func getTableName(table string, tablePrefix string) string {
	if table == "raw" {
		return config.ClickHouseStacksTable
	}
	if table == "1day_historical" {
		return fmt.Sprintf("%s_1day", config.ClickHouseStacksTable)
	}
	return fmt.Sprintf("%s_%s%s", config.ClickHouseStacksTable, table, tablePrefix)
}

func scanFrames(rows *sql.Rows, frames map[uint64]Frame, collapsed bool) (int, int, error) {
	minValue := 0
	idx := 0
	for rows.Next() {
		var hash, parentHash uint64
		var samples int
		var name string
		err := rows.Scan(&hash, &name, &parentHash, &samples)
		idx += 1
		if err != nil {
			log.Printf("error scan result: %v", err)
			continue
		}
		if minValue == 0 || samples < minValue {
			minValue = samples
		}
		isRoot := parentHash == 0
		if frame, ok := frames[hash]; ok {
			frame.Samples += samples
			frames[hash] = frame
		} else {
			frames[hash] = Frame{Hash: hash, ParentHash: parentHash, Name: name, Childrens: make(map[uint64]bool),
				Samples: samples, IsRoot: isRoot}
		}
	}
	if idx == 0 {
		if err := rows.Err(); err != nil {
			return idx, minValue, err
		}
	}
	return idx, minValue, nil
}

func (c *ClickHouseClient) GetTopFrames(ctx context.Context, params common.FlameGraphParams,
	filterQuery common.QueryFilter) (Graph, error) {
	var wg sync.WaitGroup
	var mutex sync.Mutex
	queryErrors := make([]error, 0)

	graph := NewGraph(params)
	allTimeRanges := GetTimeRanges(params.StartDateTime, params.EndDateTime, params.Resolution)
	tablePrefix, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType,
		params.K8SObject, filterQuery)

	for table, timeRanges := range allTimeRanges {
		log.Printf("🔍 Service %d: Querying table type '%s' with %d time ranges", params.ServiceId, table, len(timeRanges))
		for _, timeRange := range timeRanges {
			wg.Add(1)
			tableNew := getTableName(table, tablePrefix)
			go func(sTable string, sStart string, sEnd string) {
				defer wg.Done()
				query := fmt.Sprintf(`
				SELECT CallStackHash, any(CallStackName), any(CallStackParent), sum(NumSamples)
				AS SumNumSamples FROM %s
					WHERE ServiceId == @service_id AND (Timestamp BETWEEN @start_time AND @end_time) %s
					GROUP BY CallStackHash
					ORDER BY SumNumSamples DESC
					LIMIT @stacks_num`, sTable, conditions.Clause)

				queryStart := time.Now()
				log.Printf("🚀 Service %d: Starting query on %s (%s to %s)", params.ServiceId, sTable, sStart, sEnd)
				rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
					sql.Named("service_id", params.ServiceId),
					sql.Named("start_time", sStart),
					sql.Named("end_time", sEnd),
					sql.Named("stacks_num", params.StacksNum),
				)...)
				queryDuration := time.Since(queryStart)

				if err == nil {
					defer rows.Close()
					frames := make(map[uint64]Frame)
					nRows, minValue, scanErr := scanFrames(rows, frames, params.Format == "collapsed_file")
					err = scanErr
					// TODO: We need better solution here
					if nRows < params.StacksNum {
						minValue = 0
					}
					graph.updateFrames(frames, minValue)
					log.Printf("✅ Service %d: Query completed on %s in %v - fetched %d rows", params.ServiceId, sTable, queryDuration, nRows)
				} else {
					log.Printf("❌ Service %d: Query failed on %s after %v: %v", params.ServiceId, sTable, queryDuration, err)
				}
				mutex.Lock()
				queryErrors = append(queryErrors, err)
				mutex.Unlock()
			}(tableNew, timeRange.Start, timeRange.End)
		}
	}

	wg.Wait()

	for _, elemErr := range queryErrors {
		if elemErr != nil {
			return Graph{}, fmt.Errorf("unable fetch flamegraph from DB")
		}
	}

	_, err := graph.prepareFrames(params.StacksNum)

	if err != nil {
		return Graph{}, err
	}

	return graph, nil
}

func (c *ClickHouseClient) FetchInstanceTypeCount(ctx context.Context, params common.QueryParams,
	filterQuery common.QueryFilter) []common.InstanceTypeCount {
	var selectQuery string
	result := make([]common.InstanceTypeCount, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	selectQuery = `
		SELECT InstanceType, COUNT(DISTINCT HostName) as InstanceCount
		FROM flamedb.samples_1min where ServiceId = @service_id
		AND (Timestamp BETWEEN @start_time AND @end_time)
		%s GROUP BY InstanceType  ORDER BY InstanceCount DESC`

	query := fmt.Sprintf(selectQuery, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var instanceType string
			var instanceCount int
			err = rows.Scan(&instanceType, &instanceCount)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			if instanceType != "" {
				result = append(result, common.InstanceTypeCount{InstanceType: instanceType, InstanceCount: instanceCount})
			}
		}
	} else {
		log.Println(err)
	}
	return result
}

func (c *ClickHouseClient) FetchFieldValueSample(ctx context.Context, field string, params common.QueryParams,
	filterQuery common.QueryFilter) []common.FilterData {
	var selectQuery string
	result := make([]common.FilterData, 0)
	if _, ok := queryFields[field]; !ok {
		log.Printf("unsupported query field %q", field)
		return result
	}
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	selectQuery = `
		SELECT %s, SUM(NumSamples) as samples from flamedb.samples_1min WHERE ServiceId == @service_id AND
		(Timestamp BETWEEN @start_time AND @end_time) %s GROUP BY %s ORDER BY samples DESC;`
	query := fmt.Sprintf(selectQuery, field, conditions.Clause, field)

	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var value string
			var numSamples int
			err = rows.Scan(&value, &numSamples)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			if value == "" {
				continue
			}
			result = append(result, common.FilterData{Name: value, Samples: numSamples})
		}
	} else {
		log.Println(err)
	}
	return result
}

func (c *ClickHouseClient) FetchFieldValues(ctx context.Context, field string, params common.QueryParams,
	filterQuery common.QueryFilter) []common.FilterData {
	result := make([]common.FilterData, 0)
	if _, ok := queryFields[field]; !ok {
		log.Printf("unsupported query field %q", field)
		return result
	}
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	query := fmt.Sprintf(`
				SELECT %s from flamedb.samples_1min WHERE ServiceId == @service_id AND
				(Timestamp BETWEEN @start_time AND @end_time) %s GROUP BY %s;
			`, field, conditions.Clause, field)

	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var value string
			err = rows.Scan(&value)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			if value != "" {
				result = append(result, common.FilterData{Name: value})
			}
		}
		err = rows.Err()
	} else {
		log.Println(err)
	}
	return result
}

func (c *ClickHouseClient) FetchSampleCount(ctx context.Context, params common.QueryParams,
	filterQuery common.QueryFilter) []common.Sample {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	interval := getInterval(params.StartDateTime, params.EndDateTime, params.Interval)
	result := make([]common.Sample, 0)
	query := fmt.Sprintf(`
			SELECT toStartOfInterval(Timestamp, INTERVAL @interval) as Datetime, SUM(NumSamples)
                 FROM flamedb.samples_1min
                 WHERE ServiceId == @service_id AND (Timestamp BETWEEN @start_time AND @end_time) %s
                 GROUP BY Datetime
                 ORDER BY Datetime DESC;
	`, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("interval", interval),
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var timestamp time.Time
			var samples int
			err = rows.Scan(&timestamp, &samples)
			if err != nil {
				log.Printf("error scan result: %v", err)
			} else {
				result = append(result, common.Sample{Time: timestamp, Samples: samples})
			}
		}
		err = rows.Err()
	} else {
		log.Println(err)
	}
	return result
}

func (c *ClickHouseClient) FetchSampleCountByFunction(ctx context.Context, params common.QueryParams,
	filterQuery common.QueryFilter) []common.SamplesCountByFunction {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	interval := getInterval(params.StartDateTime, params.EndDateTime, "")
	if interval == "15 second" || interval == "30 second" {
		interval = "1 minute"
	}
	result := make([]common.SamplesCountByFunction, 0)
	query := fmt.Sprintf(`
		WITH all_samples as(
			SELECT toStartOfInterval(Timestamp, INTERVAL @interval) AS Datetime, SUM(NumSamples) AS sum_cpu
			FROM flamedb.samples_1min
			WHERE ServiceId == @service_id AND (Timestamp BETWEEN @start_time AND @end_time) %s
			GROUP BY Datetime
			ORDER BY Datetime DESC
		), function_samples AS (
			SELECT toStartOfInterval(Timestamp, INTERVAL @interval) AS Datetime, SUM(NumSamples) AS sum_cpu
			FROM  flamedb.samples
			WHERE ServiceId == @service_id AND (Timestamp BETWEEN @start_time AND @end_time)
				AND (CallStackName = @function_name) %s
			GROUP BY Datetime
			ORDER BY Datetime DESC
		)

		SELECT (function_samples.sum_cpu/all_samples.sum_cpu) AS Samples , all_samples.Datetime AS Datetime
		FROM all_samples
		LEFT JOIN function_samples ON function_samples.Datetime = all_samples.Datetime;
	`, conditions.Clause, conditions.Clause)

	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("interval", interval),
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
		sql.Named("function_name", params.FunctionName),
	)...)
	if err == nil {
		defer rows.Close()

		for rows.Next() {
			var timestamp time.Time
			var samples float64
			err = rows.Scan(&samples, &timestamp)
			if err != nil {
				log.Printf("error scan result: %v", err)
			} else {
				result = append(result, common.SamplesCountByFunction{Time: timestamp, Percentage: samples})
			}
		}
		err = rows.Err()
	} else {
		log.Println(err)
	}

	isEmpty := true
	for _, v := range result {
		if v.Percentage != 0 {
			isEmpty = false
			break
		}
	}

	if isEmpty {
		return []common.SamplesCountByFunction{}
	}

	return result
}

func (c *ClickHouseClient) FetchTimes(ctx context.Context, params common.QueryParams,
	filterQuery common.QueryFilter) []string {
	var interval string
	result := make([]string, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)

	switch params.Resolution {
	case "raw":
		interval = "1 minute"
	case "hour":
		interval = "1 hour"
	case "day":
		interval = "24 hour"
	default:
		interval = getInterval(params.StartDateTime, params.EndDateTime, "")
	}
	query := fmt.Sprintf(`
			SELECT toStartOfInterval(Timestamp, INTERVAL @interval) as Datetime
			from flamedb.samples_1min WHERE ServiceId == @service_id AND
			(Timestamp BETWEEN @start_time AND @end_time) %s
			GROUP BY Datetime
			ORDER BY Datetime DESC;`, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("interval", interval),
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var value string
			err = rows.Scan(&value)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			result = append(result, value)
		}
		err = rows.Err()
	} else {
		log.Printf("unable to execute query %v\n", err)
	}
	sort.Strings(result)
	return result
}

func (c *ClickHouseClient) FetchTimeRange(ctx context.Context, params common.QueryParams,
	filterQuery common.QueryFilter) []string {
	result := make([]string, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)

	query := fmt.Sprintf(`
			SELECT min(Timestamp), max(Timestamp)
			from flamedb.samples_1min WHERE
			ServiceId == @service_id AND
			(Timestamp BETWEEN @start_time AND @end_time) %s;`, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var startTimestamp, endTimestamp string
			err = rows.Scan(&startTimestamp, &endTimestamp)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			endTimeDate, dateErr := time.Parse(common.UTCTimeFormat, endTimestamp)
			if dateErr != nil {
				log.Printf("Error parsing end time: %v", dateErr)
			}
			fixedEndTimeDate := endTimeDate.Add(time.Minute)
			result = append(result, startTimestamp, fixedEndTimeDate.Format(common.UTCTimeFormat))
		}
		err = rows.Err()
	} else {
		log.Printf("unable to execute query %v\n", err)
	}
	sort.Strings(result)
	return result
}

func (c *ClickHouseClient) FetchMetricsSummary(ctx context.Context, params common.MetricsSummaryParams,
	filterQuery common.QueryFilter) (common.MetricsSummary, error) {
	defaultEmptyList := make([]string, 0)
	_, conditions := BuildConditions(defaultEmptyList, params.HostName, params.InstanceType, defaultEmptyList, filterQuery)

	percentile := float64(params.Percentile) / 100.0
	query := fmt.Sprintf(`
		SELECT arrayAvg(flatten(groupArray(CPUArray))), MAX(MaxCPU),
		AVG(MaxMemory), MAX(MaxMemory), quantile(@percentile)(MaxMemory), count() FROM
		(SELECT
			MAX(MemoryAverageUsedPercent) AS MaxMemory,
			MAX(CPUAverageUsedPercent) as MaxCPU,
			groupArray(CPUAverageUsedPercent) as CPUArray
		FROM %s
		WHERE ServiceId = @service_id AND (Timestamp BETWEEN @start_time AND @end_time) %s
		GROUP BY HostName)`, config.ClickHouseMetricsTable, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("percentile", percentile),
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer func(rows *sql.Rows) {
			err := rows.Close()
			if err != nil {
				log.Printf("unable to close rows: %v\n", err)
			}
		}(rows)
		for rows.Next() {
			var avgCpu float64
			var maxCpu float64
			var avgMemory float64
			var maxMemory float64
			var percentileMemory float64
			var uniqHostnames int
			err = rows.Scan(&avgCpu, &maxCpu, &avgMemory, &maxMemory, &percentileMemory, &uniqHostnames)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			if uniqHostnames == 0 {
				return common.MetricsSummary{}, errors.New("no metrics are found for given service")
			}
			return common.MetricsSummary{
				AvgCpu:           avgCpu,
				MaxCpu:           maxCpu,
				AvgMemory:        avgMemory,
				MaxMemory:        maxMemory,
				PercentileMemory: percentileMemory,
				UniqHostnames:    uniqHostnames,
			}, nil
		}
		err = rows.Err()
	} else {
		log.Printf("unable to execute query %v\n", err)
	}
	return common.MetricsSummary{}, err
}

func (c *ClickHouseClient) FetchMetricsServicesListSummary(ctx context.Context,
	params common.MetricsServicesListSummaryParams) ([]common.MetricsServicesListSummary, error) {

	percentile := float64(params.Percentile) / 100.0

	query := fmt.Sprintf(`
	WITH LatestServices AS (
		SELECT
			ServiceId as s_id, max(Timestamp) as last_seen
		FROM %s
		WHERE ServiceId in (@service_ids) AND (Timestamp BETWEEN @start_time AND @end_time)
		GROUP BY ServiceId
	), GroupedMetrics AS (
		SELECT
			ServiceId,
				max(MemoryAverageUsedPercent) AS MaxMemory,
				max(CPUAverageUsedPercent) as MaxCPU,
			groupArray(CPUAverageUsedPercent) as CPUArray
			FROM %s
			GLOBAL JOIN LatestServices ON ServiceId = s_id
			WHERE ServiceId in (@service_ids) AND (Timestamp BETWEEN last_seen - toIntervalHour(24) AND last_seen)
			GROUP BY HostName, ServiceId
		)
		SELECT arrayAvg(flatten(groupArray(CPUArray))), max(MaxCPU), ServiceId,
			   avg(MaxMemory), max(MaxMemory), quantile(@percentile)(MaxMemory), count()
		FROM GroupedMetrics
		GROUP BY ServiceId`, config.ClickHouseMetricsTable, config.ClickHouseMetricsTable)
	rows, err := c.client.QueryContext(ctx, query,
		sql.Named("service_ids", params.ServicesList),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
		sql.Named("percentile", percentile),
	)

	var results []common.MetricsServicesListSummary

	if err == nil {
		defer func(rows *sql.Rows) {
			err := rows.Close()
			if err != nil {
				log.Printf("unable to close rows: %v\n", err)
			}
		}(rows)
		for rows.Next() {
			var avgCpu float64
			var maxCpu float64
			var avgMemory float64
			var maxMemory float64
			var percentileMemory float64
			var uniqHostnames int
			var serviceId int
			err = rows.Scan(&avgCpu, &maxCpu, &serviceId, &avgMemory, &maxMemory, &percentileMemory, &uniqHostnames)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			if uniqHostnames == 0 {
				return []common.MetricsServicesListSummary{}, errors.New("no metrics are found for given services")
			}
			results = append(results, common.MetricsServicesListSummary{
				MetricsSummary: common.MetricsSummary{
					AvgCpu:           avgCpu,
					MaxCpu:           maxCpu,
					AvgMemory:        avgMemory,
					MaxMemory:        maxMemory,
					PercentileMemory: percentileMemory,
					UniqHostnames:    uniqHostnames,
				},
				ServiceId: serviceId,
			})

		}
		err = rows.Err()
	} else {
		log.Printf("unable to execute query %v\n", err)
	}
	return results, err
}

func (c *ClickHouseClient) FetchMetricsGraph(ctx context.Context, params common.MetricsSummaryParams,
	filterQuery common.QueryFilter) ([]common.MetricsSummary, error) {
	defaultEmptyList := make([]string, 0)
	_, conditions := BuildConditions(defaultEmptyList, params.HostName, params.InstanceType, defaultEmptyList, filterQuery)

	result := make([]common.MetricsSummary, 0)
	interval := getInterval(params.StartDateTime, params.EndDateTime, params.Interval)

	percentile := float64(params.Percentile) / 100.0

	groupBy := ""
	if params.GroupBy == "instance_type" {
		groupBy = ", instance_type"
	}
	query := fmt.Sprintf(`
		SELECT Datetime %s, arrayAvg(flatten(groupArray(CPUArray))), MAX(MaxCPU),
			AVG(MaxMemory), MAX(MaxMemory), quantile(@percentile)(MaxMemory) FROM
		(SELECT toStartOfInterval(Timestamp, INTERVAL @interval) as
			Datetime %s,
			HostName,
			MAX(MemoryAverageUsedPercent) AS MaxMemory,
			MAX(CPUAverageUsedPercent) as MaxCPU,
			groupArray(CPUAverageUsedPercent) as CPUArray
		FROM %s
		WHERE ServiceId = @service_id AND (Datetime BETWEEN @start_time AND @end_time) %s
		GROUP BY Datetime %s, HostName) GROUP BY Datetime %s ORDER BY Datetime DESC;
	`, groupBy, groupBy, config.ClickHouseMetricsTable, conditions.Clause, groupBy, groupBy)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("percentile", percentile),
		sql.Named("interval", interval),
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer func(rows *sql.Rows) {
			err := rows.Close()
			if err != nil {
				log.Printf("unable to close rows: %v\n", err)
			}
		}(rows)
		for rows.Next() {
			var timestamp time.Time
			var groupedBy string
			var avgCpu float64
			var maxCpu float64
			var avgMemory float64
			var maxMemory float64
			var percentileMemory float64
			var groupedByPtr *string
			if params.GroupBy != "none" {
				err = rows.Scan(&timestamp, &groupedBy, &avgCpu, &maxCpu, &avgMemory, &maxMemory, &percentileMemory)
				groupedByPtr = &groupedBy
			} else {
				err = rows.Scan(&timestamp, &avgCpu, &maxCpu, &avgMemory, &maxMemory, &percentileMemory)
			}
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			result = append(result, common.MetricsSummary{
				AvgCpu:           avgCpu,
				MaxCpu:           maxCpu,
				AvgMemory:        avgMemory,
				MaxMemory:        maxMemory,
				PercentileMemory: percentileMemory,
				GroupedBy:        groupedByPtr,
				Time:             &timestamp,
			})
		}
		err = rows.Err()
	} else {
		log.Printf("unable to execute query %v\n", err)
	}
	return result, err
}

func (c *ClickHouseClient) FetchMetricsCpuTrend(ctx context.Context, params common.MetricsCpuTrendParams,
	filterQuery common.QueryFilter) (common.MetricsCpuTrend, error) {
	defaultEmptyList := make([]string, 0)
	finalResult := common.MetricsCpuTrend{}
	_, conditions := BuildConditions(defaultEmptyList, params.HostName, params.InstanceType, defaultEmptyList, filterQuery)

	query := fmt.Sprintf(`
		WITH CURRENT_CONSUMPTION AS (
			SELECT
				arrayAvg(flatten(groupArray(CPUArray))) AS avg_cpu,
				MAX(MaxCPU) AS max_cpu,
				AVG(MaxMemory) AS avg_memory,
				MAX(MaxMemory) AS max_memory,
				1 SortOrder
			FROM
				(SELECT
				MAX(MemoryAverageUsedPercent) AS MaxMemory,
					MAX(CPUAverageUsedPercent) as MaxCPU,
					groupArray(CPUAverageUsedPercent) as CPUArray
					FROM %s
					WHERE ServiceId = @service_id AND
						(Timestamp BETWEEN @start_time AND @end_time) %s
					GROUP BY HostName)
			),
		PREVIOUS_CONSUMPTION AS (
			SELECT
				arrayAvg(flatten(groupArray(CPUArray))) AS avg_cpu,
				MAX(MaxCPU) AS max_cpu,
				AVG(MaxMemory) AS avg_memory,
				MAX(MaxMemory) AS max_memory,
				2 SortOrder
			FROM
			(SELECT
				MAX(MemoryAverageUsedPercent) AS MaxMemory,
					MAX(CPUAverageUsedPercent) as MaxCPU,
					groupArray(CPUAverageUsedPercent) as CPUArray
				FROM %s
				WHERE ServiceId = @service_id AND
					(Timestamp BETWEEN @compared_start_time AND @compared_end_time) %s
				GROUP BY HostName)
			)
			SELECT avg_cpu, max_cpu, avg_memory, max_memory
			FROM (
					SELECT * FROM CURRENT_CONSUMPTION
					UNION ALL
					SELECT * FROM PREVIOUS_CONSUMPTION)
				order by SortOrder`, config.ClickHouseMetricsTable, conditions.Clause,
		config.ClickHouseMetricsTable, conditions.Clause)

	first := true
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
		sql.Named("compared_start_time", params.ComparedStartDateTime),
		sql.Named("compared_end_time", params.ComparedEndDateTime),
	)...)
	if err == nil {
		defer func(rows *sql.Rows) {
			err := rows.Close()
			if err != nil {
				log.Printf("unable to close rows: %v\n", err)
			}
		}(rows)
		for rows.Next() {
			var avgCpu float64
			var maxCpu float64
			var avgMemory float64
			var maxMemory float64
			err = rows.Scan(&avgCpu, &maxCpu, &avgMemory, &maxMemory)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}

			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			avgMemory = convertNumToZeroIfNotValid(avgMemory)
			maxMemory = convertNumToZeroIfNotValid(maxMemory)
			maxCpu = convertNumToZeroIfNotValid(maxCpu)
			avgCpu = convertNumToZeroIfNotValid(avgCpu)

			if first {
				finalResult.MaxCpu = maxCpu
				finalResult.AvgCpu = avgCpu
				finalResult.MaxMemory = maxMemory
				finalResult.AvgMemory = avgMemory
				first = false
			} else {
				finalResult.ComparedMaxCpu = maxCpu
				finalResult.ComparedAvgCpu = avgCpu
				finalResult.ComparedMaxMemory = maxMemory
				finalResult.ComparedAvgMemory = avgMemory
			}
		}
		err = rows.Err()
	} else {
		log.Printf("unable to execute query %v\n", err)
	}
	return finalResult, err
}

func (c *ClickHouseClient) FetchServices(ctx context.Context, params common.ServicesParams) []SrvResp {
	expr := "(ServiceId)"
	groupByExpr := "GROUP BY (ServiceId)"
	if params.WithDeployments {
		expr = "(ServiceId,ContainerEnvName)"
		groupByExpr = "GROUP BY (ServiceId,ContainerEnvName)"
	}
	query := fmt.Sprintf(`
		SELECT %s from flamedb.samples_1min
		WHERE (Timestamp BETWEEN @start_time AND @end_time) %s;
	`, expr, groupByExpr)
	rows, err := c.client.QueryContext(ctx, query,
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)
	result := make([]SrvResp, 0)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var tuple []interface{}
			err = rows.Scan(&tuple)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			if params.WithDeployments {
				result = append(result, SrvResp{
					ServiceId:  tuple[1].(uint32),
					Deployment: tuple[2].(string),
				})
			} else {
				result = append(result, SrvResp{ServiceId: tuple[1].(uint32)})
			}
		}
		err = rows.Err()
	} else {
		log.Println(err)
	}
	return result
}

func (c *ClickHouseClient) FetchSessionsCount(ctx context.Context, params common.SessionsCountParams,
	filterQuery common.QueryFilter) (int, error) {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)

	query := fmt.Sprintf(`
		SELECT uniq(HostName,Timestamp) FROM flamedb.samples_1min WHERE ServiceId = @service_id AND
			(Timestamp BETWEEN @start_time AND @end_time) %s;
	`, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var sessionCount int
			err = rows.Scan(&sessionCount)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			return sessionCount, nil
		}
		err = rows.Err()
	} else {
		log.Println(err)
	}
	return 0, err
}

func (c *ClickHouseClient) FetchLastHTML(ctx context.Context, params common.MetricsLastHTMLParams,
	filterQuery common.QueryFilter) (string, error) {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	query := fmt.Sprintf(`
			SELECT argMax(HTMLPath,Timestamp) FROM flamedb.metrics WHERE ServiceId = @service_id AND
				(Timestamp BETWEEN @start_time AND @end_time) %s;
		`, conditions.Clause)
	rows, err := c.client.QueryContext(ctx, query, withFilterArgs(conditions,
		sql.Named("service_id", params.ServiceId),
		sql.Named("start_time", params.StartDateTime),
		sql.Named("end_time", params.EndDateTime),
	)...)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var htmlPath string
			err = rows.Scan(&htmlPath)
			if err != nil {
				log.Printf("error scan result: %v", err)
			}
			return htmlPath, nil
		}
		err = rows.Err()
	} else {
		log.Println(err)
	}
	return "", nil
}
