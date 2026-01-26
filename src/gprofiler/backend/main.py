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

from backend import routers
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException


def format_time(dt: datetime):
    iso_format = dt.isoformat()
    if "+" in iso_format:
        return iso_format.replace("+00:00", "Z") if "+00:00" in iso_format else iso_format
    return iso_format + "Z"


app = FastAPI(openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_, exc):
    if exc.status_code == 204:
        return Response(status_code=204)
    return JSONResponse(exc.detail, status_code=exc.status_code)


app.include_router(routers.router, prefix="/api")
