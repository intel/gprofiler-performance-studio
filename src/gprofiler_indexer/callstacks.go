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
	"bufio"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go/aws/session"
	log "github.com/sirupsen/logrus"
)

// Profiling type constants
const (
	ProfilingTypeAdhoc      = "adhoc"
	ProfilingTypeContinuous = "continuous"
)

type FrameValuesMap map[string]map[string]FrameValue

type FrameValue struct {
	Weight int
}

type Frame struct {
	Name string
	Hash string
	Prev string
}

type FileInfo struct {
	Metadata struct {
		Hostname   string `json:"hostname"`
		Continuous bool   `json:"continuous"`
		CloudInfo  struct {
			InstanceType string `json:"instance_type"`
		} `json:"cloud_info"`
		RunArguments struct {
			ServiceName       string `json:"service_name"`
			ProfileApiVersion string `json:"profile_api_version"`
			PerfEvents        string `json:"perf_events"`
			PerfMode          string `json:"perf_mode"`
		} `json:"run_arguments"`
	} `json:"metadata"`
	HTMLBlob       string `json:"htmlblob"`
	FlamegraphHTML string `json:"flamegraph_html"`
	Metrics        struct {
		CPUAvg    float64 `json:"cpu_avg"`
		MemoryAvg float64 `json:"mem_avg"`
	} `json:"metrics"`
	ApplicationMetadataEnabled bool `json:"application_metadata_enabled"`
}

func isSwapper(stack []string) bool {
	if len(stack) > 0 && strings.HasPrefix(stack[0], "swapper") {
		return true
	}
	return false
}

func extractStack(line string, withContainer bool, withMetadata bool) (int, string, []string) {
	var rawContainerName string
	var skipIndex int

	line = strings.TrimSpace(line)
	temp := strings.Split(line, " ")
	sampleCount, _ := strconv.Atoi(temp[len(temp)-1])
	line = strings.Join(temp[:len(temp)-1], " ")

	frames := strings.Split(line, ";")
	stack := make([]string, 0, len(frames))

	if withContainer {
		if withMetadata {
			rawContainerName = frames[1]
			skipIndex = 2
		} else {
			rawContainerName = frames[0]
			skipIndex = 1
		}
	} else {
		rawContainerName = ""
		skipIndex = 0
	}

	line = strings.Join(frames[skipIndex:], ";")
	if frameReplacer.ShouldNormalize(line) {
		line = frameReplacer.NormalizeString(line)
	}
	frames = strings.Split(line, ";")

	for _, frame := range frames {
		frame = strings.TrimSpace(frame)
		if frame != "" {
			stack = append(stack, frame)
		}
	}

	return sampleCount, rawContainerName, stack
}

func parseStackFileMeta(line string) (FileInfo, bool, error) {
	fileInfo := FileInfo{}
	var withMetadata bool
	err := json.Unmarshal([]byte(line[1:]), &fileInfo)
	if err != nil {
		logger.Errorf("error while parsing json header %v", err)
		return fileInfo, withMetadata, err
	}
	withMetadata = fileInfo.ApplicationMetadataEnabled
	return fileInfo, withMetadata, nil
}

func processStack(stack []string, sampleCount int, rawContainerName string, frameValues FrameValuesMap,
	frames map[string]Frame) {

	key := rawContainerName

	if frameValues[key] == nil {
		frameValues[key] = make(map[string]FrameValue)
	}

	frameIdx := 0
	prevFrame := ""
	for idx, frame := range stack {
		var hashFrame string
		if idx > 0 {
			hashFrame = GetHash(strings.Join(stack[0:idx+1], ":"))
		} else {
			hashFrame = GetHash(frame)
		}
		f := Frame{
			Name: frame,
			Hash: hashFrame,
			Prev: prevFrame,
		}
		frames[hashFrame] = f
		frameValue := frameValues[key][hashFrame]
		frameValue.Weight += sampleCount
		frameValues[key][hashFrame] = frameValue
		prevFrame = hashFrame
		frameIdx += 1
	}
}

type ProfilesWriter struct {
	chMutex        sync.Mutex
	stacksRecords  chan StackRecord
	metricsRecords chan MetricRecord
}

func NewProfilesWriter(channels *RecordChannels) *ProfilesWriter {
	return &ProfilesWriter{
		stacksRecords:  channels.StacksRecords,
		metricsRecords: channels.MetricsRecords,
	}
}

func (pw *ProfilesWriter) writeStacks(weights FrameValuesMap, frames map[string]Frame,
	serviceId uint32, instanceType string, hostname string, timestamp time.Time) {
	idx := 0
	for rawContainerName, containerWeights := range weights {
		containerName, k8sName, _ := ContainerAndK8sName(rawContainerName)

		for hash, weightVal := range containerWeights {
			frame := frames[hash]
			prevHashAsInt, _ := strconv.ParseUint(frame.Prev, 16, 64)
			if frame.Prev == "" {
				prevHashAsInt = 0
			}
			hashAsInt, _ := strconv.ParseUint(hash, 16, 64)
			if frame.Prev != "" {
				parentWeightVal := containerWeights[frame.Prev]
				if weightVal.Weight > parentWeightVal.Weight {
					logger.Debugf("Glitch: %s (%d) > %s (%d)",
						frame.Name,
						weightVal.Weight,
						frame.Prev,
						parentWeightVal.Weight)
				}
			}
			record := StackRecord{
				Timestamp:          timestamp,
				ServiceId:          serviceId,
				InstanceType:       instanceType,
				ContainerEnvName:   k8sName,
				HostName:           hostname,
				ContainerName:      containerName,
				NumSamples:         weightVal.Weight,
				CallStackHash:      hashAsInt,
				Parent:             prevHashAsInt,
				Name:               frame.Name,
				InsertionTimestamp: time.Now().UTC(),
			}
			pw.stacksRecords <- record
			idx += 1
		}
	}
	logger.Debugf("write %d records to BufferedClickHouseWrite", idx)
}

func (pw *ProfilesWriter) writeMetrics(serviceId uint32, instanceType string,
	hostname string, timestamp time.Time, cpuAverageUsedPercent float64,
	memoryAverageUsedPercent float64, path string) {

	metricRecord := MetricRecord{
		Timestamp:                timestamp,
		ServiceId:                serviceId,
		InstanceType:             instanceType,
		HostName:                 hostname,
		CPUAverageUsedPercent:    cpuAverageUsedPercent,
		MemoryAverageUsedPercent: memoryAverageUsedPercent,
		HTMLPath:                 path,
	}
	log.Debugf("DEBUG: Sending metric record to channel - ServiceId=%d, HostName=%s, HTMLPath=%s", 
		serviceId, hostname, path)
	pw.metricsRecords <- metricRecord
	log.Debugf("DEBUG: Metric record sent to channel successfully")
}

func (pw *ProfilesWriter) ParseStackFrameFile(sess *session.Session, task SQSMessage, s3bucket string,
	timestamp time.Time, buf []byte) error {
	var fileInfo FileInfo
	var withMetadata bool
	var err error
	serviceId := task.ServiceId
	logger.Debugf("start processing file with len %d from %d", len(buf), serviceId)

	weights := make(FrameValuesMap)
	mapFrames := make(map[string]Frame)
	scanner := bufio.NewScanner(strings.NewReader(string(buf)))
	scannerBuf := make([]byte, 0, ScannerBufSize)
	scanner.Buffer(scannerBuf, MaxScannerBufSize)

	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "#") {
			fileInfo, withMetadata, err = parseStackFileMeta(line)
			if err != nil {
				return err
			}
		} else {
			withContainer := fileInfo.Metadata.RunArguments.ProfileApiVersion != V1Prefix
			sampleCount, rawContainerName, stack := extractStack(line, withContainer, withMetadata)
			if isSwapper(stack) {
				continue
			}
			if sampleCount == 0 {
				continue
			}
			processStack(stack, sampleCount, rawContainerName, weights, mapFrames)
		}
	}
	err = scanner.Err()
	if err != nil {
		logger.Errorf("Error while reading file: %v", err)
	}

	nRecords := 0
	for _, v := range weights {
		nRecords += len(v)
	}

	logger.Debugf("end processing file %d, record(s) to insert %d, uniq frame(s) %d", serviceId,
		nRecords, len(mapFrames))
	pw.chMutex.Lock()
	pw.writeStacks(weights, mapFrames, uint32(serviceId),
		fileInfo.Metadata.CloudInfo.InstanceType, fileInfo.Metadata.Hostname, timestamp)
	pw.chMutex.Unlock()

	var htmlBlobPath string
	if fileInfo.HTMLBlob != "" {
		baseFileName := strings.TrimSuffix(task.Filename, ".gz")
		htmlBlobPath = fmt.Sprintf("products/%s/stacks/%s.html", task.Service, baseFileName)
		decodedBlob, err := base64.StdEncoding.DecodeString(fileInfo.HTMLBlob)
		if err != nil {
			log.Errorf("failed to decode base64 HTML blob for file %s: %v", task.Filename, err)
		} else {
			err = PutFileToS3(sess, s3bucket, htmlBlobPath, decodedBlob)
			if err != nil {
				log.Errorf("failed to upload HTML blob for file %s: %v", task.Filename, err)
			}
		}
	}

	// Save flamegraph HTML if present (dedicated flamegraph HTML separate from the stack blob)
	if fileInfo.FlamegraphHTML != "" {
		baseFileName := strings.TrimSuffix(task.Filename, ".gz")

		// Replace hostname hash with actual hostname in the filename
		// Format: <start_time_iso_format>_<random_suffix>_<hostname_hash> -> <start_time_iso_format>_<random_suffix>_<hostname>
		parts := strings.Split(baseFileName, "_")
		if len(parts) >= 3 {
			// Replace the last part (hostname hash) with actual hostname
			parts[len(parts)-1] = fileInfo.Metadata.Hostname
			baseFileName = strings.Join(parts, "_")
		}

		// Determine profiling type based on metadata.continuous
		profilingType := ProfilingTypeAdhoc
		if fileInfo.Metadata.Continuous {
			profilingType = ProfilingTypeContinuous
		}

		flamegraphHTMLPath := fmt.Sprintf("products/%s/stacks/flamegraph/%s_%s_flamegraph.html", task.Service, baseFileName, profilingType)

		var flamegraphData []byte
		// Try to decode as base64, if it fails, treat it as plain HTML
		decodedFlamegraph, err := base64.StdEncoding.DecodeString(fileInfo.FlamegraphHTML)
		if err != nil {
			log.Warnf("flamegraph HTML for file %s is not base64-encoded, treating as plain HTML", task.Filename)
			flamegraphData = []byte(fileInfo.FlamegraphHTML)
		} else {
			flamegraphData = decodedFlamegraph
		}

		err = PutFileToS3(sess, s3bucket, flamegraphHTMLPath, flamegraphData)
		if err != nil {
			log.Errorf("failed to upload flamegraph HTML for file %s: %v", task.Filename, err)
		} else {
			log.Infof("successfully uploaded flamegraph HTML to %s", flamegraphHTMLPath)

			// Store metadata in PostgreSQL for all adhoc profiles
			if profilingType == ProfilingTypeAdhoc {
				// Extract perf_events from profile metadata only if perf_mode is enabled
				var perfEvents []string
				perfMode := fileInfo.Metadata.RunArguments.PerfMode
				if perfMode != "disabled" {
					perfEventsStr := fileInfo.Metadata.RunArguments.PerfEvents
					if perfEventsStr != "" {
						// Split comma-separated string into array
						for _, event := range strings.Split(perfEventsStr, ",") {
							trimmed := strings.TrimSpace(event)
							if trimmed != "" {
								perfEvents = append(perfEvents, trimmed)
							}
						}
					}
				}

				// Store metadata for all adhoc profiles (perf_events will be empty array if perf_mode is not enabled)
				err = StoreAdhocFlamegraphMetadata(
					task.ServiceId,
					fileInfo.Metadata.Hostname,
					flamegraphHTMLPath,
					perfEvents,
					timestamp,
					int64(len(flamegraphData)),
				)
				if err != nil {
					log.Errorf("failed to store flamegraph metadata for %s: %v", flamegraphHTMLPath, err)
					// Don't fail the entire operation if metadata storage fails
				} else {
					log.Infof("successfully stored metadata for %s with events: %v",
						flamegraphHTMLPath, perfEvents)
				}
			}
		}
	}

	log.Debugf("DEBUG: hostname=%s, htmlBlobPath='%s', CPUAvg=%f, MemoryAvg=%f",
		fileInfo.Metadata.Hostname, htmlBlobPath, fileInfo.Metrics.CPUAvg, fileInfo.Metrics.MemoryAvg)

	if htmlBlobPath != "" || (fileInfo.Metrics.CPUAvg != 0 && fileInfo.Metrics.MemoryAvg != 0) {
		log.Debugf("DEBUG: Writing metrics for hostname=%s", fileInfo.Metadata.Hostname)
		pw.writeMetrics(uint32(serviceId), fileInfo.Metadata.CloudInfo.InstanceType,
			fileInfo.Metadata.Hostname, timestamp, fileInfo.Metrics.CPUAvg,
			fileInfo.Metrics.MemoryAvg, htmlBlobPath)
	} else {
		log.Debugf("DEBUG: SKIPPING metrics write for hostname=%s - condition failed", fileInfo.Metadata.Hostname)
	}

	return nil
}
