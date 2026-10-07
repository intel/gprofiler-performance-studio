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

import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from typing import Optional

from backend.config import FLAMEGRAPH_PATH
from backend.models.filters_models import RQLFilter

TIME_RANGE_MAP = {
    24 * 60 * 60: "daily",
    24 * 60 * 60 * 7: "weekly",
    6 * 60 * 60: "6hour",
    60 * 60: "hourly",
    30 * 60: "30min",
    15 * 60: "15min",
}


def get_svg_file(collapsed_file_data: str):
    _, temp_collapsed_file = tempfile.mkstemp()
    with open(temp_collapsed_file, "w") as file:
        file.write(collapsed_file_data)
    cmd = [f"{FLAMEGRAPH_PATH}/flamegraph.pl", "--inverted", "--colors=combined", temp_collapsed_file]
    output = subprocess.check_output(cmd)
    return BytesIO(output)


def get_file_name(
    start_time: datetime,
    end_time: datetime,
    service_name: str,
    suffix: str = "svg",
    rql_filter: Optional[RQLFilter] = None,
):
    delta_in_seconds = int((end_time - start_time).total_seconds())
    file_time_range_name = TIME_RANGE_MAP.get(delta_in_seconds, "custom")
    filter_str = ""
    if rql_filter:
        filter_str = f"_{rql_filter.get_formatted_filter()}"
    file_name = f"{service_name}_{file_time_range_name}{filter_str}.{suffix}"
    return file_name
