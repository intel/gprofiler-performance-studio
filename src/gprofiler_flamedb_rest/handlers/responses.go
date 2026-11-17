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

package handlers

import (
	"restflamedb/common"
	"restflamedb/db"
	"time"
)

type ExecTimeInterface interface {
	SetExecTime(time.Time)
}

type ExecTimeResponse struct {
	ExecTime float64 `json:"exec_time"`
}

func (et *ExecTimeResponse) SetExecTime(start time.Time) {
	et.ExecTime = float64(time.Since(start)) / float64(time.Second)
}

type QueryResponse struct {
	Result []string `json:"result"`
	ExecTimeResponse
}

type AnyResponse struct {
	Result any `json:"result"`
	ExecTimeResponse
}

type ServiceResponse struct {
	Result []db.SrvResp `json:"result"`
	ExecTimeResponse
}

type SessionsResponse struct {
	Result int `json:"result"`
	ExecTimeResponse
}

type MetricsSummaryResponse struct {
	Result common.MetricsSummary `json:"result"`
	ExecTimeResponse
}

type MetricsServicesListSummaryResponse struct {
	Result []common.MetricsServicesListSummary `json:"result"`
	ExecTimeResponse
}

type SampleCountResponse struct {
	Result []common.Sample `json:"result"`
	ExecTimeResponse
}

type SampleCountByFunctionResponse struct {
	Result []common.SamplesCountByFunction `json:"result"`
	ExecTimeResponse
}

type InstanceTypeCountResponse struct {
	Result []common.InstanceTypeCount `json:"result"`
	ExecTimeResponse
}

type FieldValueSampleResponse struct {
	Result []common.FilterData `json:"result"`
	ExecTimeResponse
}

type MetricsGraphResponse struct {
	Result []common.MetricsSummary `json:"result"`
	ExecTimeResponse
}

type MetricsExtNamesResponse struct {
	Result []string `json:"result"`
	ExecTimeResponse
}

type MetricsExtGraphResponse struct {
	Result []common.MetricsExtPoint `json:"result"`
	ExecTimeResponse
}

type MetricsCpuResponse struct {
	Result common.MetricsCpuTrend `json:"result"`
	ExecTimeResponse
}

type MetricsHTMLResponse struct {
	Result string `json:"result"`
	ExecTimeResponse
}

type FlameGraphResponse struct {
	Name     string             `json:"name"`
	Value    int                `json:"value"`
	Children []db.ResponseFrame `json:"children"`
	ExecTimeResponse
	OlapTime    float64           `json:"olap_time"`
	Percentiles map[string]string `json:"percentiles"`
}
