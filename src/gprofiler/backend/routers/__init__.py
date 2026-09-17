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

from backend.routers import (
    api_key_routes,
    filters_routes,
    flamegraph_routes,
    healthcheck_routes,
    installations_routes,
    metrics_routes,
    minesweeper_routes,
    overview_routes,
    perfspect_routes,
    profiles_routes,
    services_routes,
)
from fastapi import APIRouter

router = APIRouter()
router.include_router(healthcheck_routes.router, prefix="/v1/health_check", tags=["agent"])
router.include_router(healthcheck_routes.router, prefix="/v2/health_check", tags=["agent"])
router.include_router(flamegraph_routes.router, prefix="/flamegraph", tags=["flamegraph"])
router.include_router(metrics_routes.router, prefix="/metrics", tags=["metrics"])
router.include_router(installations_routes.router, prefix="/installations", tags=["app"])
router.include_router(api_key_routes.router, prefix="/api_key", tags=["auth"])
router.include_router(profiles_routes.router, prefix="/v2/profiles", tags=["agent"])
router.include_router(services_routes.router, prefix="/services", tags=["app"])
router.include_router(filters_routes.router, prefix="/v1/filters", tags=["filters"])
router.include_router(overview_routes.router, prefix="/overview", tags=["overview"])
router.include_router(minesweeper_routes.router, prefix="/snapshots", tags=["snapshots"])
router.include_router(perfspect_routes.router, prefix="/perfspect", tags=["perfspect"])
