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

"""
Dynamic Profiling Data Models

This module contains Pydantic models for the dynamic profiling feature, which allows
profiling requests at various hierarchy levels (service, job, namespace) to be mapped
to specific host-level commands while maintaining sub-second heartbeat response times.

References:
https://docs.google.com/document/d/1iwA_NN1YKDBqfig95Qevw0HcSCqgu7_ya8PGuCksCPc/edit
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ============================================================
# ENUMS
# ============================================================

class CommandType(str, Enum):
    """Command types for profiling operations"""
    START = "start"
    STOP = "stop"
    RECONFIGURE = "reconfigure"


class ProfilingStatus(str, Enum):
    """Status for profiling requests and executions"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProfilingMode(str, Enum):
    """Profiling modes supported by the system"""
    CPU = "cpu"
    MEMORY = "memory"
    ALLOCATION = "allocation"
    NATIVE = "native"


# ============================================================
# REQUEST MODELS
# ============================================================

class ProfilingRequestCreate(BaseModel):
    """
    Request model for creating a new profiling request via API.
    At least one target specification must be provided.
    """
    # Target specification (at least one required)
    service_name: Optional[str] = None
    job_name: Optional[str] = None
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    host_name: Optional[str] = None
    process_id: Optional[int] = None

    # Profiling configuration
    profiling_mode: ProfilingMode = ProfilingMode.CPU
    duration_seconds: int = Field(gt=0, description="Duration in seconds, must be positive")
    sample_rate: int = Field(default=100, ge=1, le=1000, description="Sample rate (1-1000)")

    # Execution configuration
    executors: List[str] = Field(default_factory=list)

    # Request metadata
    start_time: datetime
    stop_time: Optional[datetime] = None
    mode: Optional[str] = None

    @field_validator('duration_seconds')
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("duration_seconds must be positive")
        return v

    def model_post_init(self, __context: Any) -> None:
        """Validate that at least one target is specified"""
        targets = [
            self.service_name,
            self.job_name,
            self.namespace,
            self.pod_name,
            self.host_name,
            self.process_id,
        ]
        if not any(targets):
            raise ValueError("At least one target specification must be provided")


class ProfilingRequestResponse(BaseModel):
    """Response model for profiling request"""
    id: int
    request_id: UUID
    service_name: Optional[str] = None
    job_name: Optional[str] = None
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    host_name: Optional[str] = None
    process_id: Optional[int] = None
    profiling_mode: ProfilingMode
    duration_seconds: int
    sample_rate: int
    executors: List[str]
    start_time: datetime
    stop_time: Optional[datetime] = None
    mode: Optional[str] = None
    status: ProfilingStatus
    created_at: datetime
    updated_at: datetime
    profiler_token_id: Optional[int] = None

    class Config:
        from_attributes = True


class ProfilingRequestUpdate(BaseModel):
    """Model for updating profiling request status"""
    status: Optional[ProfilingStatus] = None
    stop_time: Optional[datetime] = None


# ============================================================
# COMMAND MODELS
# ============================================================

class ProfilingCommandCreate(BaseModel):
    """Model for creating a profiling command to be sent to agents"""
    profiling_request_id: int
    host_id: str
    target_containers: List[str] = Field(default_factory=list)
    target_processes: List[int] = Field(default_factory=list)
    command_type: CommandType
    command_args: Dict[str, Any] = Field(default_factory=dict)
    command_json: Optional[str] = None


class ProfilingCommandResponse(BaseModel):
    """Response model for profiling command"""
    id: int
    command_id: UUID
    profiling_request_id: int
    host_id: str
    target_containers: List[str]
    target_processes: List[int]
    command_type: CommandType
    command_args: Dict[str, Any]
    command_json: Optional[str] = None
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: ProfilingStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProfilingCommandUpdate(BaseModel):
    """Model for updating profiling command"""
    status: Optional[ProfilingStatus] = None
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    command_json: Optional[str] = None


# ============================================================
# HEARTBEAT MODELS
# ============================================================

class HostHeartbeatCreate(BaseModel):
    """
    Model for creating/updating host heartbeat.
    Optimized for 165k QPM with sub-second response times.
    """
    host_id: str
    service_name: Optional[str] = None
    host_name: str
    host_ip: Optional[str] = None
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    containers: List[str] = Field(default_factory=list)
    workloads: Dict[str, Any] = Field(default_factory=dict)
    jobs: List[str] = Field(default_factory=list)
    executors: List[str] = Field(default_factory=list)
    last_command_id: Optional[UUID] = None


class HostHeartbeatResponse(BaseModel):
    """Response model for host heartbeat"""
    id: int
    host_id: str
    service_name: Optional[str] = None
    host_name: str
    host_ip: Optional[str] = None
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    containers: List[str]
    workloads: Dict[str, Any]
    jobs: List[str]
    executors: List[str]
    timestamp_first_seen: datetime
    timestamp_last_seen: datetime
    last_command_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HostHeartbeatUpdate(BaseModel):
    """Model for updating host heartbeat (typically just timestamp)"""
    timestamp_last_seen: datetime
    last_command_id: Optional[UUID] = None
    containers: Optional[List[str]] = None
    workloads: Optional[Dict[str, Any]] = None
    jobs: Optional[List[str]] = None
    executors: Optional[List[str]] = None


# ============================================================
# EXECUTION MODELS
# ============================================================

class ProfilingExecutionCreate(BaseModel):
    """Model for creating profiling execution audit entry"""
    profiling_request_id: int
    profiling_command_id: Optional[int] = None
    host_name: str
    target_containers: List[str] = Field(default_factory=list)
    target_processes: List[int] = Field(default_factory=list)
    command_type: CommandType
    started_at: datetime
    status: ProfilingStatus


class ProfilingExecutionResponse(BaseModel):
    """Response model for profiling execution"""
    id: int
    execution_id: UUID
    profiling_request_id: int
    profiling_command_id: Optional[int] = None
    host_name: str
    target_containers: List[str]
    target_processes: List[int]
    command_type: CommandType
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: ProfilingStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProfilingExecutionUpdate(BaseModel):
    """Model for updating profiling execution"""
    status: Optional[ProfilingStatus] = None
    completed_at: Optional[datetime] = None


# ============================================================
# MAPPING TABLE MODELS
# ============================================================

class NamespaceServiceMapping(BaseModel):
    """Model for namespace to service mapping"""
    namespace: str
    service_name: str


class NamespaceServiceMappingResponse(NamespaceServiceMapping):
    """Response model for namespace service mapping"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ServiceContainerMapping(BaseModel):
    """Model for service to container mapping"""
    service_name: str
    container_name: str


class ServiceContainerMappingResponse(ServiceContainerMapping):
    """Response model for service container mapping"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobContainerMapping(BaseModel):
    """Model for job to container mapping"""
    job_name: str
    container_name: str


class JobContainerMappingResponse(JobContainerMapping):
    """Response model for job container mapping"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContainerProcessMapping(BaseModel):
    """Model for container to process mapping"""
    container_name: str
    process_id: int
    process_name: Optional[str] = None


class ContainerProcessMappingResponse(ContainerProcessMapping):
    """Response model for container process mapping"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContainerHostMapping(BaseModel):
    """Model for container to host mapping"""
    container_name: str
    host_id: str
    host_name: str


class ContainerHostMappingResponse(ContainerHostMapping):
    """Response model for container host mapping"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProcessHostMapping(BaseModel):
    """Model for process to host mapping"""
    process_id: int
    host_id: str
    host_name: str


class ProcessHostMappingResponse(ProcessHostMapping):
    """Response model for process host mapping"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# QUERY MODELS
# ============================================================

class ProfilingRequestQuery(BaseModel):
    """Query parameters for listing profiling requests"""
    status: Optional[ProfilingStatus] = None
    service_name: Optional[str] = None
    namespace: Optional[str] = None
    host_name: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class HostHeartbeatQuery(BaseModel):
    """
    Query parameters for listing host heartbeats.
    Optimized for fast queries to support 165k QPM.
    """
    service_name: Optional[str] = None
    namespace: Optional[str] = None
    host_id: Optional[str] = None
    last_seen_after: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ProfilingExecutionQuery(BaseModel):
    """Query parameters for listing profiling executions"""
    profiling_request_id: Optional[int] = None
    host_name: Optional[str] = None
    status: Optional[ProfilingStatus] = None
    started_after: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)




