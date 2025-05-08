#
# Copyright (C) 2023 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from datetime import datetime
from typing import Optional

from backend.models import CamelModel
from pydantic import BaseModel


class SampleCount(BaseModel):
    samples: int
    time: datetime


class InstanceTypeCount(BaseModel):
    instance_count: int
    instance_type: str


class Metric(BaseModel):
    avg_cpu: Optional[float]
    avg_memory: Optional[float]
    max_cpu: Optional[float]
    max_memory: Optional[float]
    percentile_memory: Optional[float]


class CpuTrend(BaseModel):
    avg_cpu: float
    max_cpu: float
    avg_memory: float
    max_memory: float
    compared_avg_cpu: float
    compared_max_cpu: float
    compared_avg_memory: float
    compared_max_memory: float


class CpuMetric(BaseModel):
    cpu_percentage: float
    time: datetime


class MetricNodesAndCores(BaseModel):
    avg_nodes: float
    max_nodes: float
    avg_cores: float
    max_cores: float
    time: datetime


class MetricSummary(Metric):
    uniq_hostnames: Optional[int]


class MetricGraph(Metric):
    uniq_hostnames: Optional[int]
    time: datetime


class MetricNodesCoresSummary(BaseModel):
    avg_cores: float
    avg_nodes: Optional[float]


class MetricK8s(CamelModel):
    name: str
    samples: Optional[int] = None
    cores: Optional[int] = None
    cpu: Optional[float] = None
    memory: Optional[float] = None


class HTMLMetadata(CamelModel):
    content: str
