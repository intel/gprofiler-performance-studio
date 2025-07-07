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

import math
import uuid
from datetime import datetime, timedelta
from logging import getLogger
from typing import List, Optional, Dict, Any

from botocore.exceptions import ClientError

from backend.models.filters_models import FilterTypes
from backend.models.flamegraph_models import FGParamsBaseModel
from backend.models.metrics_models import (
    CpuMetric,
    CpuTrend,
    InstanceTypeCount,
    MetricGraph,
    MetricNodesAndCores,
    MetricNodesCoresSummary,
    MetricSummary,
    SampleCount,
    HTMLMetadata,
)
from backend.utils.filters_utils import get_rql_first_eq_key, get_rql_only_for_one_key
from backend.utils.request_utils import flamegraph_base_request_params, get_metrics_response, get_query_response
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from gprofiler_dev import S3ProfileDal
from gprofiler_dev.postgres.db_manager import DBManager

logger = getLogger(__name__)
router = APIRouter()


class ProfilingRequest(BaseModel):
    """Model for profiling request parameters"""
    service_name: str
    duration: Optional[int] = 60  # seconds
    frequency: Optional[int] = 11  # Hz
    profiling_mode: Optional[str] = "cpu"  # cpu, allocation, none
    target_hostnames: Optional[List[str]] = None
    pids: Optional[List[int]] = None
    additional_args: Optional[Dict[str, Any]] = None


class ProfilingResponse(BaseModel):
    """Response model for profiling requests"""
    success: bool
    message: str
    request_id: Optional[str] = None
    estimated_completion_time: Optional[datetime] = None


class HeartbeatRequest(BaseModel):
    """Model for host heartbeat request"""
    ip_address: str
    hostname: str
    service_name: str
    last_command_id: Optional[str] = None
    status: Optional[str] = "active"  # active, idle, error
    timestamp: Optional[datetime] = None


class HeartbeatResponse(BaseModel):
    """Response model for heartbeat requests"""
    success: bool
    message: str
    profiling_request: Optional[ProfilingRequest] = None
    command_id: Optional[str] = None


def get_time_interval_value(start_time: datetime, end_time: datetime, interval: str) -> str:
    if interval in [
        "15 seconds",
        "30 seconds",
        "1 minutes",
        "5 minutes",
        "15 minutes",
        "1 hours",
        "2 hours",
        "6 hours",
        "24 hours",
    ]:
        return interval
    diff = end_time - start_time
    value = diff.total_seconds()
    if value <= 60 * 30:  # half an hour
        return "15 seconds"
    if value <= 60 * 60:  # hour
        return "30 seconds"
    if value <= 60 * 60 * 24:  # day
        return "15 minutes"
    if value <= 60 * 60 * 24 * 7:  # week
        return "2 hours"
    if value <= 60 * 60 * 24 * 14:  # 2 weeks
        return "6 hours"
    return "24 hours"


@router.get("/instance_type_count", response_model=List[InstanceTypeCount])
def get_instance_type_count(fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params)):
    response = get_query_response(fg_params, lookup_for="instance_type_count")
    res = []
    for row in response:
        res.append(
            {
                "instance_count": row.get("instance_count", 0),
                "instance_type": row.get("instance_type", "").split("/")[-1],
            }
        )
    return res


@router.get("/samples", response_model=List[SampleCount])
def get_flamegraph_samples_count(
    requested_interval: Optional[str] = "",
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    return get_query_response(fg_params, lookup_for="samples", interval=requested_interval)


@router.get(
    "/graph", response_model=List[MetricGraph], responses={204: {"description": "Good request, just has no data"}}
)
def get_flamegraph_metrics_graph(
    requested_interval: Optional[str] = "",
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)
    if deployment_name:
        return Response(status_code=204)
    fg_params.filter = get_rql_only_for_one_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
    return get_metrics_response(fg_params, lookup_for="graph", interval=requested_interval)


@router.get(
    "/function_cpu",
    response_model=List[CpuMetric],
    responses={204: {"description": "Good request, just has no data"}},
)
def get_function_cpu_overtime(
    function_name: str = Query(..., alias="functionName"),
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    fg_params.function_name = function_name
    return get_query_response(fg_params, lookup_for="samples_count_by_function")


@router.get(
    "/graph/nodes_and_cores",
    response_model=List[MetricNodesAndCores],
    responses={204: {"description": "Good request, just has no data"}},
)
def get_flamegraph_nodes_cores_graph(
    requested_interval: str = "",
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)
    container_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.CONTAINER_KEY)
    host_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)

    if deployment_name or container_name_value:
        return Response(status_code=204)

    db_manager = DBManager()
    service_id = db_manager.get_service_id_by_name(fg_params.service_name)
    parsed_interval_value = get_time_interval_value(fg_params.start_time, fg_params.end_time, requested_interval)
    return db_manager.get_nodes_and_cores_graph(
        service_id, fg_params.start_time, fg_params.end_time, parsed_interval_value, host_name_value
    )


@router.get(
    "/summary",
    response_model=MetricSummary,
    response_model_exclude_none=True,
    responses={204: {"description": "Good request, just has no data"}},
)
def get_metrics_summary(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)

    if not deployment_name:  # hostname before deployment or no filters at all
        fg_params.filter = get_rql_only_for_one_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
        return get_metrics_response(fg_params, lookup_for="summary")

    return Response(status_code=204)


@router.get(
    "/nodes_cores/summary",
    response_model=MetricNodesCoresSummary,
    response_model_exclude_none=True,
    responses={204: {"description": "Good request, just has no data"}},
)
def get_nodes_and_cores_metrics_summary(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
    ignore_zeros: bool = Query(False, alias="ignoreZeros"),
):
    db_manager = DBManager()
    deployment_name = get_rql_first_eq_key(fg_params.filter, FilterTypes.K8S_OBJ_KEY)
    if not deployment_name:  # hostname before deployment or no filters at all

        service_id = db_manager.get_service_id_by_name(fg_params.service_name)
        host_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
        res = db_manager.get_nodes_cores_summary(
            service_id, fg_params.start_time, fg_params.end_time, ignore_zeros=ignore_zeros, hostname=host_name_value
        )
        if res["avg_cores"] is None and res["avg_nodes"] is None:
            return Response(status_code=204)
        return res

    return Response(status_code=204)


@router.get("/cpu_trend", response_model=CpuTrend)
def calculate_trend_in_cpu(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    diff_in_days: int = (fg_params.end_time - fg_params.start_time).days
    diff_in_hours: float = (fg_params.end_time - fg_params.start_time).seconds / 3600
    diff_in_weeks = timedelta(weeks=1)

    # if the time range is longer then onw week we would like to increase the delta in x +1 weeks from the current range
    if diff_in_days >= 7:
        weeks = math.ceil(diff_in_days / 7)
        # If it is exactly X weeks diff, verify that it is exactly X weeks diff without hours, otherwise add 1 week
        if diff_in_days % 7 == 0 and diff_in_hours > 0:
            weeks += 1
        diff_in_weeks = timedelta(weeks=weeks)
    compared_start_date = fg_params.start_time - diff_in_weeks
    compared_end_date = fg_params.end_time - diff_in_weeks

    response = get_metrics_response(
        fg_params,
        lookup_for="cpu_trend",
        compared_start_datetime=compared_start_date.strftime("%Y-%m-%dT%H:%M:%S"),
        compared_end_datetime=compared_end_date.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    return response


@router.get("/html_metadata", response_model=HTMLMetadata)
def get_html_metadata(
    fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
):
    host_name_value = get_rql_first_eq_key(fg_params.filter, FilterTypes.HOSTNAME_KEY)
    if not host_name_value:
        raise HTTPException(400, detail="Must filter by hostname to get the html metadata")
    s3_path = get_metrics_response(fg_params, lookup_for="lasthtml")
    if not s3_path:
        raise HTTPException(404, detail="The html metadata path not found in CH")
    s3_dal = S3ProfileDal(logger)
    try:
        html_content = s3_dal.get_object(s3_path, is_gzip=True)
    except ClientError:
        raise HTTPException(status_code=404, detail="The html metadata file not found in S3")
    return HTMLMetadata(content=html_content)


@router.post("/profile_request", response_model=ProfilingResponse)
def create_profiling_request(profiling_request: ProfilingRequest):
    """
    Create a new profiling request with the specified parameters.
    
    This endpoint accepts profiling arguments in JSON format and initiates
    a profiling session based on the provided configuration.
    """
    try:
        # Validate the profiling mode
        valid_modes = ["cpu", "allocation", "none"]
        if profiling_request.profiling_mode not in valid_modes:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid profiling mode. Must be one of: {valid_modes}"
            )
        
        # Validate duration (must be positive)
        if profiling_request.duration and profiling_request.duration <= 0:
            raise HTTPException(
                status_code=400,
                detail="Duration must be a positive integer (seconds)"
            )
        
        # Validate frequency (must be positive)
        if profiling_request.frequency and profiling_request.frequency <= 0:
            raise HTTPException(
                status_code=400,
                detail="Frequency must be a positive integer (Hz)"
            )
        
        # Log the profiling request
        logger.info(
            f"Received profiling request for service: {profiling_request.service_name}",
            extra={
                "service_name": profiling_request.service_name,
                "duration": profiling_request.duration,
                "frequency": profiling_request.frequency,
                "mode": profiling_request.profiling_mode,
                "target_hostnames": profiling_request.target_hostnames,
                "pids": profiling_request.pids
            }
        )
        
        # TODO: Implement actual profiling logic here
        # This is where you would:
        # 1. Save the profiling request arguments to PostgreSQL DB for tracking and audit purposes
        # 2. Queue the profiling request
        # 3. Initiate profiling on target hosts/processes
        # 4. Return a request ID for tracking
        
        # Generate a mock request ID for now
        import uuid
        request_id = str(uuid.uuid4())
        
        # Calculate estimated completion time
        completion_time = datetime.now() + timedelta(seconds=profiling_request.duration or 60)
        
        return ProfilingResponse(
            success=True,
            message=f"Profiling request submitted successfully for service '{profiling_request.service_name}'",
            request_id=request_id,
            estimated_completion_time=completion_time
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to create profiling request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error while processing profiling request"
        )


@router.post("/heartbeat", response_model=HeartbeatResponse)
def receive_heartbeat(heartbeat: HeartbeatRequest):
    """
    Receive heartbeat from host and check for pending profiling requests.
    
    This endpoint:
    1. Receives heartbeat information from hosts (IP, hostname, service, last command)
    2. Updates host status in PostgreSQL DB
    3. Checks for pending profiling requests for this host/service
    4. Returns new profiling request if available and not already executed
    """
    try:
        # Set timestamp if not provided
        if heartbeat.timestamp is None:
            heartbeat.timestamp = datetime.now()
        
        # Log the heartbeat
        logger.info(
            f"Received heartbeat from host: {heartbeat.hostname} ({heartbeat.ip_address})",
            extra={
                "hostname": heartbeat.hostname,
                "ip_address": heartbeat.ip_address,
                "service_name": heartbeat.service_name,
                "last_command_id": heartbeat.last_command_id,
                "status": heartbeat.status,
                "timestamp": heartbeat.timestamp
            }
        )
        
        # TODO: Implement actual heartbeat and profiling request logic here
        # This is where you would:
        # 1. Update host heartbeat information in PostgreSQL DB (hosts table)
        # 2. Check for pending profiling requests for this host/service in PostgreSQL DB
        # 3. Filter requests that haven't been executed yet (not in last_command_id)
        # 4. Mark the profiling request as assigned/in-progress
        # 5. Return the profiling request details to the host
        
        db_manager = DBManager()
        
        # Mock logic for now - check if there's a pending profiling request
        # In real implementation, this would query the profiling_requests table
        pending_request = None
        command_id = None
        
        # Example query logic (to be implemented):
        # pending_request = db_manager.get_pending_profiling_request(
        #     hostname=heartbeat.hostname,
        #     service_name=heartbeat.service_name,
        #     exclude_command_id=heartbeat.last_command_id
        # )
        
        if pending_request:
            # Generate command ID for this profiling request
            command_id = str(uuid.uuid4())
            
            # Mark request as assigned (to be implemented)
            # db_manager.mark_profiling_request_assigned(pending_request.id, command_id, heartbeat.hostname)
            
            return HeartbeatResponse(
                success=True,
                message="Heartbeat received. New profiling request available.",
                profiling_request=pending_request,
                command_id=command_id
            )
        else:
            return HeartbeatResponse(
                success=True,
                message="Heartbeat received. No pending profiling requests.",
                profiling_request=None,
                command_id=None
            )
        
    except Exception as e:
        logger.error(f"Failed to process heartbeat: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error while processing heartbeat"
        )
