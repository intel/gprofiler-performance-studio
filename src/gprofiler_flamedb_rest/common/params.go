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

package common

import (
	"time"
)

type TimeParams struct {
	StartDateTime time.Time `form:"start_datetime" time_format:"2006-01-02T15:04:05" time_utc:"1"`
	EndDateTime   time.Time `form:"end_datetime" time_format:"2006-01-02T15:04:05" time_utc:"1"`
}

func (params *TimeParams) CheckTimeRange() {
	if params.EndDateTime == ZeroTime {
		params.EndDateTime = time.Now().UTC().Add(-BackRewindTime)
	}
	if params.StartDateTime == ZeroTime {
		params.StartDateTime = params.EndDateTime.Add(-time.Hour * 24)
	}
}

type AllFiltersParams struct {
	ContainerName []string `form:"container"`
	HostName      []string `form:"hostname"`
	InstanceType  []string `form:"instance_type"`
	K8SObject     []string `form:"k8s_obj"`
}

type FiltersParams struct {
	ContainerName string `rql:"column=ContainerName,filter"`
	HostName      string `rql:"column=HostName,filter"`
	InstanceType  string `rql:"column=InstanceType,filter"`
	K8SObject     string `rql:"column=ContainerEnvName,filter"`
}

type MetricsFiltersParams struct {
	HostName     string `rql:"column=HostName,filter"`
	InstanceType string `rql:"column=InstanceType,filter"`
}

type FlameGraphParams struct {
	TimeParams
	AllFiltersParams
	ServiceId  int               `form:"service" binding:"required"`
	Filter     string            `form:"filter"`
	StacksNum  int               `form:"stacks_num,default=10000"`
	Sample     int               `form:"sample,default=1"`
	Resolution string            `form:"resolution,default=multi" binding:"oneof=multi hour day raw"`
	Format     string            `form:"format,default=flamegraph" binding:"oneof=flamegraph collapsed_file"`
	Enrichment []string          `form:"enrichment"`
	Insights   map[string]string `form:"insights"`
}

type QueryParams struct {
	TimeParams
	AllFiltersParams
	ServiceId    int    `form:"service" binding:"required"`
	FunctionName string `form:"function_name"`
	Filter       string `form:"filter"`
	Resolution   string `form:"resolution,default=hour" binding:"oneof=none hour day raw"`
	Interval     string `form:"interval"`
	LookupFor    string `form:"lookup_for" binding:"required,oneof=ContainerName container HostName hostname InstanceType instance_type ContainerEnvName k8s_obj time time_range instance_type_count samples samples_count_by_function"`
}

type ClientParams struct {
	ClientId int `form:"client" binding:"required"`
	TimeParams
}

type ServicesParams struct {
	TimeParams
	WithDeployments bool `form:"with_deployments,default=false"`
}

type SessionsCountParams struct {
	TimeParams
	AllFiltersParams
	ServiceId int    `form:"service" binding:"required"`
	Filter    string `form:"filter"`
}

type MetricsSummaryParams struct {
	TimeParams
	ServiceId    int      `form:"service" binding:"required"`
	Filter       string   `form:"filter"`
	Percentile   int      `form:"percentile,default=90" binding:"numeric,min=0,max=100"`
	HostName     []string `form:"hostname"`
	InstanceType []string `form:"instance_type"`
	Interval     string   `form:"interval"`
	GroupBy      string   `form:"group_by,default=none" binding:"oneof=none instance_type`
}

type MetricsCpuTrendParams struct {
	TimeParams
	ServiceId             int       `form:"service" binding:"required"`
	ComparedStartDateTime time.Time `form:"compared_start_datetime" time_format:"2006-01-02T15:04:05" time_utc:"1"`
	ComparedEndDateTime   time.Time `form:"compared_end_datetime" time_format:"2006-01-02T15:04:05" time_utc:"1"`
	Filter                string    `form:"filter"`
	HostName              []string  `form:"hostname"`
	InstanceType          []string  `form:"instance_type"`
}

type MetricsServicesListSummaryParams struct {
	ServicesList []int `json:"services_ids"`
	ClientsList  []int `json:"clients_ids"`
	TimeParams
	Percentile int `form:"percentile,default=90" binding:"numeric,min=0,max=100"`
}

type Sample struct {
	Time    time.Time `json:"time"`
	Samples int       `json:"samples"`
}

type SamplesCountByFunction struct {
	Time       time.Time `json:"time"`
	Percentage float64   `json:"cpu_percentage"`
}

type MetricsSummary struct {
	AvgCpu              float64    `json:"avg_cpu"`
	MaxCpu              float64    `json:"max_cpu"`
	AvgMemory           float64    `json:"avg_memory"`
	MaxMemory           float64    `json:"max_memory"`
	PercentileMemory    float64    `json:"percentile_memory"`
	AvgFrequency        *float64   `json:"avg_frequency,omitempty"`
	MaxFrequency        *float64   `json:"max_frequency,omitempty"`
	AvgCPICount         *float64   `json:"avg_cpi_count,omitempty"`
	MaxCPICount         *float64   `json:"max_cpi_count,omitempty"`
	AvgTMAFrontEndBound *float64   `json:"avg_tma_front_end_bound,omitempty"`
	MaxTMAFrontEndBound *float64   `json:"max_tma_front_end_bound,omitempty"`
	AvgTMABackendBound  *float64   `json:"avg_tma_backend_bound,omitempty"`
	MaxTMABackendBound  *float64   `json:"max_tma_backend_bound,omitempty"`
	AvgTMABadSpec       *float64   `json:"avg_tma_bad_spec,omitempty"`
	MaxTMABadSpec       *float64   `json:"max_tma_bad_spec,omitempty"`
	AvgTMARetiring      *float64   `json:"avg_tma_retiring,omitempty"`
	MaxTMARetiring      *float64   `json:"max_tma_retiring,omitempty"`
	UniqHostnames       int        `json:"uniq_hostnames,omitempty"`
	GroupedBy           *string    `json:"grouped_by,omitempty"`
	Time                *time.Time `json:"time,omitempty"`
}

type MetricsCpuTrend struct {
	AvgCpu            float64 `json:"avg_cpu"`
	MaxCpu            float64 `json:"max_cpu"`
	AvgMemory         float64 `json:"avg_memory"`
	MaxMemory         float64 `json:"max_memory"`
	ComparedAvgCpu    float64 `json:"compared_avg_cpu"`
	ComparedMaxCpu    float64 `json:"compared_max_cpu"`
	ComparedAvgMemory float64 `json:"compared_avg_memory"`
	ComparedMaxMemory float64 `json:"compared_max_memory"`
}

type FilterData struct {
	Name    string `json:"name"`
	Samples int    `json:"samples,omitempty"`
}

type InstanceTypeCount struct {
	InstanceType  string `json:"instance_type"`
	InstanceCount int    `json:"instance_count"`
}

type MetricsServicesListSummary struct {
	MetricsSummary
	ServiceId int `json:"service_id"`
}
