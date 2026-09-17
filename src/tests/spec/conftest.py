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
Shared setup for the *fast* backend unit/acceptance tests.

These tests import backend modules in-process (no running server or database),
so they need the ``backend`` and ``gprofiler_dev`` packages importable. This
conftest makes both source roots available on sys.path before collection.
"""

import sys
from pathlib import Path

# src/tests/unit/ -> parents[2] == src/
_SRC_ROOT = Path(__file__).resolve().parents[2]

for _pkg_root in (_SRC_ROOT / "gprofiler", _SRC_ROOT / "gprofiler-dev"):
    _path = str(_pkg_root)
    if _pkg_root.is_dir() and _path not in sys.path:
        sys.path.insert(0, _path)
