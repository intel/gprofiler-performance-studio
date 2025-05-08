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

import json
from datetime import datetime
from logging import getLogger
from typing import Dict, List, Optional, Union

import requests
from backend.config import QUERY_API_BASE_URL, REST_CERTIFICATE_PATH, REST_PASSWORD, REST_USERNAME, STACKS_COUNT_DEFAULT
from backend.models.common import ServiceName
from backend.models.filters_models import RQLFilter
from backend.models.flamegraph_models import FGParamsBaseModel, FGParamsModel
from backend.utils.json_param import json_param
from fastapi import Depends, HTTPException, Query
from gprofiler_dev.postgres.db_manager import DBManager
from requests import Response

logger = getLogger(__name__)


def flamegraph_base_request_params(
    service_name: ServiceName = Query(..., alias="serviceName"),
    start_time: datetime = Query(..., alias="startTime"),
    end_time: datetime = Query(..., alias="endTime"),
    fg_filter: RQLFilter = json_param("filter", RQLFilter, description="RQL format filter", default=None),
) -> FGParamsBaseModel:
    return FGParamsBaseModel(service_name=service_name, start_time=start_time, end_time=end_time, filter=fg_filter)


def flamegraph_request_params(
    base_fg_params: FGParamsBaseModel = Depends(flamegraph_base_request_params),
    enrichment: Optional[List[str]] = Query([], alias="enrichment"),
    stacks_count: int = Query(STACKS_COUNT_DEFAULT, alias="stacksCount"),
) -> FGParamsModel:
    return FGParamsModel(enrichment=enrichment, stacks_count=stacks_count, **base_fg_params.dict())


def get_result_from_response_and_extract_instance_name(response):
    result = json.loads(response.text).get("result", [])
    final = [
        {"instance_count": row.get("instance_count", 0), "instance_type": row.get("instance_type", "").split("/")[-1]}
        for row in result
    ]
    return final


def get_api_params(service_name: str, start_time: datetime, end_time: datetime, **kwargs) -> Dict:
    db_manager = DBManager()
    service_id = db_manager.get_service_id_by_name(service_name)
    if service_id is None:
        raise HTTPException(406, detail=f"service {service_name} doesn't exists")
    params = {
        "service": service_id,
        "start_datetime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_datetime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if kwargs:
        params.update({k: v for k, v in kwargs.items() if v is not None})
    return params


def get_flamegraph_response(
    fg_params: FGParamsModel,
    file_type: str = "flamegraph",
    metadata: str = None,
    stream=False,
):
    fg_filter = fg_params.filter.json().encode() if fg_params.filter else None
    db_api_params = get_api_params(
        fg_params.service_name,
        fg_params.start_time,
        fg_params.end_time,
        format=file_type,
        enrichment=fg_params.enrichment,
        stacks_num=fg_params.stacks_count,
        filter=fg_filter,
    )
    response = get_flamegraph_request(db_api_params, stream)
    return response


def get_flamegraph_request(db_api_params, stream):
    response = requests.get(
        url=f"{QUERY_API_BASE_URL}/api/v1/flamegraph",
        params=db_api_params,
        stream=stream,
        verify=REST_CERTIFICATE_PATH,
        auth=(REST_USERNAME, REST_PASSWORD),
    )
    if response.status_code >= 300:
        logger.error(response.text)
        # this error string is used in the frontend, please don't change it until we add error handling
        raise HTTPException(status_code=502, detail="Failed getting data")
    if not stream and not response.text:
        # TODO: handle properly in FE!
        raise HTTPException(status_code=204, detail="No Data")
    return response


def _common_fg_rest_response(response: Response, db_api_params: Dict) -> Union[List, Dict, str]:
    if response.status_code == 401:
        logger.error(f"{response.request.url} request is unauthorized")
    if response.status_code >= 300:
        logger.error(response.text)
        raise HTTPException(status_code=502, detail="Failed getting data")
    if response.status_code == 204:
        raise HTTPException(status_code=204)
    data = response.json()
    if not data:
        logger.error(
            "good status code but empty response from flameDB (without the expected data wrapper)",
            extra={"db_params": db_api_params},
        )
        raise HTTPException(status_code=502, detail="Failed getting data")
    if "result" not in data:
        logger.error(
            "good status code but expected result field is missing)", extra={"db_params": db_api_params, "data": data}
        )
        raise HTTPException(status_code=502, detail="Failed getting data")
    if not data["result"]:
        raise HTTPException(status_code=204)
    return data["result"]


def get_query_response(
    fg_params: FGParamsBaseModel, lookup_for: str = "time", resolution=None, interval=None
) -> Union[List, Dict, str]:
    fg_filter = fg_params.filter.json().encode() if fg_params.filter else None
    db_api_params = get_api_params(
        fg_params.service_name,
        fg_params.start_time,
        fg_params.end_time,
        function_name=fg_params.function_name,
        lookup_for=lookup_for,
        resolution=resolution,
        filter=fg_filter,
        interval=interval,
    )
    try:
        response = requests.get(
            url=f"{QUERY_API_BASE_URL}/api/v1/query",
            params=db_api_params,
            verify=REST_CERTIFICATE_PATH,
            auth=(REST_USERNAME, REST_PASSWORD),
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="Failed connect to flamedb api")
    return _common_fg_rest_response(response, db_api_params)


def get_metrics_response(
    fg_params: FGParamsBaseModel,
    lookup_for: str = "graph",
    resolution=None,
    interval=None,
    compared_start_datetime=None,
    compared_end_datetime=None,
) -> Union[List, Dict, str]:
    fg_filter = fg_params.filter.json().encode() if fg_params.filter else None
    db_api_params = get_api_params(
        fg_params.service_name,
        fg_params.start_time,
        fg_params.end_time,
        resolution=resolution,
        filter=fg_filter,
        compared_start_datetime=compared_start_datetime,
        compared_end_datetime=compared_end_datetime,
        lookup_for=lookup_for,
        interval=interval,
    )
    try:
        response = requests.get(
            url=f"{QUERY_API_BASE_URL}/api/v1/metrics/{lookup_for}",
            params=db_api_params,
            verify=REST_CERTIFICATE_PATH,
            auth=(REST_USERNAME, REST_PASSWORD),
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=502, detail="Failed connect to flamedb api")
    return _common_fg_rest_response(response, db_api_params)
