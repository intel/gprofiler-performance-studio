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
	"restflamedb/common"
	"restflamedb/config"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/ClickHouse/clickhouse-go"
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
	retentionInterval := time.Hour * 24 * 14
	now := time.Now().UTC()
	if now.Sub(start) >= retentionInterval {
		result["1day_historical"] = append(result["1day_historical"], makeTimeRange(makeStartOfDay(start), makeEndOfDay(end)))
		return result
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

	return result
}

func BuildConditions(ContainerName []string, HostName []string, InstanceType []string, K8SObject []string,
	filterQuery string) (string, string) {
	if filterQuery != "" {
		return "", filterQuery
	}
	var conditions string
	tablePrefix := "_all"

	if len(ContainerName) > 0 {
		containerNamesHash := make([]string, 0)
		for _, singleContainerName := range ContainerName {
			containerNamesHash = append(containerNamesHash, fmt.Sprint(common.GetHash32AsInt(singleContainerName)))
		}
		conditions += fmt.Sprintf(" AND (ContainerNameHash IN (%s))", strings.Join(containerNamesHash, ","))
		tablePrefix = ""
	}
	if len(HostName) > 0 {
		hostNamesHash := make([]string, 0)
		for _, singleHostName := range HostName {
			hostNamesHash = append(hostNamesHash, fmt.Sprint(common.GetHash32AsInt(singleHostName)))
		}
		conditions += fmt.Sprintf(" AND (HostNameHash IN (%s))", strings.Join(hostNamesHash, ","))
		tablePrefix = ""
	}
	if len(InstanceType) > 0 {
		tablePrefix = ""
		conditions += fmt.Sprintf(" AND (InstanceType IN ('%s'))", strings.Join(InstanceType, "','"))
	}
	if len(K8SObject) > 0 {
		tablePrefix = ""
		conditions += fmt.Sprintf(" AND (ContainerEnvName IN ('%s'))", strings.Join(K8SObject, "','"))
	}
	return tablePrefix, conditions
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
	filterQuery string) (Graph, error) {
	var wg sync.WaitGroup
	var mutex sync.Mutex
	queryErrors := make([]error, 0)

	graph := NewGraph(params)
	allTimeRanges := GetTimeRanges(params.StartDateTime, params.EndDateTime, params.Resolution)
	tablePrefix, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType,
		params.K8SObject, filterQuery)

	for table, timeRanges := range allTimeRanges {
		for _, timeRange := range timeRanges {
			wg.Add(1)
			tableNew := getTableName(table, tablePrefix)
			go func(sTable string, sStart string, sEnd string) {
				defer wg.Done()
				query := `
				SELECT CallStackHash, any(CallStackName), any(CallStackParent), sum(NumSamples)
				AS SumNumSamples FROM ?
				WHERE ServiceId == '?' AND (Timestamp BETWEEN '?' AND '?') ?
				GROUP BY CallStackHash
				ORDER BY SumNumSamples DESC
				LIMIT ?`
				log.Printf("SELECT query: ?", query)
				rows, err := c.client.Query(query, sTable, params.ServiceId, sStart, sEnd, conditions, params.StacksNum)
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
					log.Printf("Fetch %d rows", nRows)
				} else {
					log.Println(err)
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
	filterQuery string) []common.InstanceTypeCount {
	var selectQuery string
	result := make([]common.InstanceTypeCount, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	selectQuery = `
		SELECT InstanceType, COUNT(DISTINCT HostName) as InstanceCount
		FROM flamedb.samples_1min where ServiceId = '?'  AND (Timestamp BETWEEN '?'  AND '?' )
		? GROUP BY InstanceType  ORDER BY InstanceCount DESC`
	rows, err := c.client.Query(selectQuery, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), conditions)
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
	filterQuery string) []common.FilterData {
	var selectQuery string
	result := make([]common.FilterData, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	selectQuery = `
		SELECT ?, SUM(NumSamples) as samples from flamedb.samples_1min WHERE ServiceId == '?' AND
		(Timestamp BETWEEN '?' AND '?') ? GROUP BY ? ORDER BY samples DESC;`
	rows, err := c.client.Query(selectQuery,field, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), conditions, field)
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
	filterQuery string) []common.FilterData {
	result := make([]common.FilterData, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	query := `
				SELECT ? from flamedb.samples_1min WHERE ServiceId == '?' AND
				(Timestamp BETWEEN '?' AND '?') ? GROUP BY ?;
			`

	rows, err := c.client.Query(query, field, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), conditions, field)
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
	filterQuery string) []common.Sample {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	interval := getInterval(params.StartDateTime, params.EndDateTime, params.Interval)
	result := make([]common.Sample, 0)
	query := `
			SELECT toStartOfInterval(Timestamp, INTERVAL '?') as Datetime, SUM(NumSamples)
                 FROM flamedb.samples_1min
                 WHERE ServiceId == '?' AND (Timestamp BETWEEN '?' AND '?') ?
                 GROUP BY Datetime
                 ORDER BY Datetime DESC;
	`
	rows, err := c.client.Query(query, interval, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), conditions)
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
	filterQuery string) []common.SamplesCountByFunction {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	interval := getInterval(params.StartDateTime, params.EndDateTime, "")
	if interval == "15 second" || interval == "30 second" {
		interval = "1 minute"
	}
	result := make([]common.SamplesCountByFunction, 0)
	query := `
		WITH all_samples as(
			SELECT toStartOfInterval(Timestamp, INTERVAL '?') AS Datetime, SUM(NumSamples) AS sum_cpu
			FROM flamedb.samples_1min
			WHERE ServiceId == '?' AND (Timestamp BETWEEN '?' AND '?') ?
			GROUP BY Datetime
			ORDER BY Datetime DESC
		), function_samples AS (
			SELECT toStartOfInterval(Timestamp, INTERVAL '?') AS Datetime, SUM(NumSamples) AS sum_cpu
			FROM  flamedb.samples
			WHERE ServiceId == '?' AND (Timestamp BETWEEN '?' AND '?') AND (CallStackName = '?') ?
			GROUP BY Datetime
			ORDER BY Datetime DESC
		)

		SELECT (function_samples.sum_cpu/all_samples.sum_cpu) AS Samples , all_samples.Datetime AS Datetime
		FROM all_samples
		LEFT JOIN function_samples ON function_samples.Datetime = all_samples.Datetime;
	`
	rows, err := c.client.Query(query, interval, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), conditions, interval, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), params.FunctionName, conditions)
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

func (c *ClickHouseClient) FetchTimes(ctx context.Context, params common.QueryParams, filterQuery string) []string {
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
	query := `
			SELECT toStartOfInterval(Timestamp, INTERVAL '?') as Datetime
			from flamedb.samples_1min WHERE ServiceId == '?' AND
			(Timestamp BETWEEN '?' AND '?') ?
			GROUP BY Datetime
			ORDER BY Datetime DESC;`
	rows, err := c.client.Query(query, interval, params.ServiceId,
		common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), conditions)
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

func (c *ClickHouseClient) FetchTimeRange(ctx context.Context, params common.QueryParams, filterQuery string) []string {
	result := make([]string, 0)
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)

	query := `
			SELECT min(Timestamp), max(Timestamp)
			from flamedb.samples_1min WHERE
			ServiceId == '?' AND
			(Timestamp BETWEEN '?' AND '?') ?;`
	rows, err := c.client.Query(query, params.ServiceId,
		common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), conditions)
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
	filterQuery string) (common.MetricsSummary, error) {
	defaultEmptyList := make([]string, 0)
	_, conditions := BuildConditions(defaultEmptyList, params.HostName, params.InstanceType, defaultEmptyList, filterQuery)

	percentile := float64(params.Percentile) / 100.0
	query := `
		SELECT arrayAvg(flatten(groupArray(CPUArray))), MAX(MaxCPU),
		AVG(MaxMemory), MAX(MaxMemory),  quantile(?)(MaxMemory), count() FROM
		(SELECT
			MAX(MemoryAverageUsedPercent) AS MaxMemory,
			MAX(CPUAverageUsedPercent) as MaxCPU,
			groupArray(CPUAverageUsedPercent) as CPUArray
		FROM ?
		WHERE ServiceId = ? AND (Timestamp BETWEEN '?' AND '?') ?
		GROUP BY HostName)`
	rows, err := c.client.Query(query, percentile, config.ClickHouseMetricsTable, params.ServiceId,
		common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), conditions)
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

	formattedServicesList := joinIntSlice(params.ServicesList, ",")
	percentile := float64(params.Percentile) / 100.0

	query := `
	WITH LatestServices AS (
		SELECT
			ServiceId as s_id, max(Timestamp) as last_seen
		FROM ?
		WHERE ServiceId in (?) AND (Timestamp BETWEEN '?' AND '?')
		GROUP BY ServiceId
	), GroupedMetrics AS (
		SELECT
			ServiceId,
				max(MemoryAverageUsedPercent) AS MaxMemory,
				max(CPUAverageUsedPercent) as MaxCPU,
			groupArray(CPUAverageUsedPercent) as CPUArray
		FROM ?
		GLOBAL JOIN LatestServices ON ServiceId = s_id
		WHERE ServiceId in (?) AND (Timestamp BETWEEN last_seen - toIntervalHour(24) AND last_seen)
		GROUP BY HostName, ServiceId
	)
	SELECT arrayAvg(flatten(groupArray(CPUArray))), max(MaxCPU), ServiceId,
		   avg(MaxMemory), max(MaxMemory), quantile(?)(MaxMemory), count()
	FROM GroupedMetrics
	GROUP BY ServiceId`
	rows, err := c.client.Query(query, config.ClickHouseMetricsTable, formattedServicesList,
		common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime),
		config.ClickHouseMetricsTable, formattedServicesList, percentile)

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
	filterQuery string) ([]common.MetricsSummary, error) {
	defaultEmptyList := make([]string, 0)
	_, conditions := BuildConditions(defaultEmptyList, params.HostName, params.InstanceType, defaultEmptyList, filterQuery)

	result := make([]common.MetricsSummary, 0)
	interval := getInterval(params.StartDateTime, params.EndDateTime, params.Interval)

	percentile := float64(params.Percentile) / 100.0

	groupBy := ""
	if params.GroupBy != "none" {
		groupBy = fmt.Sprintf(", %s", params.GroupBy)
	}
	query := `
		SELECT Datetime ?, arrayAvg(flatten(groupArray(CPUArray))), MAX(MaxCPU),
			AVG(MaxMemory), MAX(MaxMemory), quantile(?)(MaxMemory) FROM
		(SELECT toStartOfInterval(Timestamp, INTERVAL '?') as
			Datetime ?,
			HostName,
			MAX(MemoryAverageUsedPercent) AS MaxMemory,
			MAX(CPUAverageUsedPercent) as MaxCPU,
			groupArray(CPUAverageUsedPercent) as CPUArray
		FROM ?
		WHERE ServiceId = ? AND (Datetime BETWEEN '?' AND '?') ?
		GROUP BY Datetime ?, HostName) GROUP BY Datetime ? ORDER BY Datetime DESC;
	`
	rows, err := c.client.Query(query, groupBy, percentile, interval, groupBy, config.ClickHouseMetricsTable, params.ServiceId,
		common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), conditions, groupBy, groupBy)
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
	filterQuery string) (common.MetricsCpuTrend, error) {
	defaultEmptyList := make([]string, 0)
	finalResult := common.MetricsCpuTrend{}
	_, conditions := BuildConditions(defaultEmptyList, params.HostName, params.InstanceType, defaultEmptyList, filterQuery)

	query := `
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
				FROM ?
				WHERE ServiceId = ? AND (Timestamp BETWEEN '?' AND '?') ?
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
			FROM ?
			WHERE ServiceId = ? AND (Timestamp BETWEEN '?' AND '?') ?
			GROUP BY HostName)
		)
			SELECT avg_cpu, max_cpu, avg_memory, max_memory
			FROM (
				SELECT * FROM CURRENT_CONSUMPTION
				UNION ALL
				SELECT * FROM PREVIOUS_CONSUMPTION)
			order by SortOrder`

	first := true
	rows, err := c.client.Query(query, config.ClickHouseMetricsTable, params.ServiceId,
		common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), conditions,
		config.ClickHouseMetricsTable, params.ServiceId,
		common.FormatTime(params.ComparedStartDateTime), common.FormatTime(params.ComparedEndDateTime), conditions)
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
	query := `
		SELECT ? from flamedb.samples_1min WHERE (Timestamp BETWEEN '?' AND '?') ?;
	`
	rows, err := c.client.Query(query, expr, common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), groupByExpr)
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
	filterQuery string) (int, error) {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)

	query := `
		SELECT uniq(HostName,Timestamp) FROM flamedb.samples_1min WHERE ServiceId = ? AND
		                                                                (Timestamp BETWEEN '?' AND '?') ?;
	`
	rows, err := c.client.Query(query, params.ServiceId, common.FormatTime(params.StartDateTime),
		common.FormatTime(params.EndDateTime), conditions)
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
	filterQuery string) (string, error) {
	_, conditions := BuildConditions(params.ContainerName, params.HostName, params.InstanceType, params.K8SObject, filterQuery)
	query := `
			SELECT argMax(HTMLPath,Timestamp) FROM flamedb.metrics WHERE ServiceId = ? AND
			                                                                (Timestamp BETWEEN '?' AND '?') ?;
		`
	rows, err := c.client.Query(query, params.ServiceId, common.FormatTime(params.StartDateTime), common.FormatTime(params.EndDateTime), conditions)
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
