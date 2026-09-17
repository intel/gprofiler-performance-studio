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
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.models import CamelModel
from gprofiler_dev.tags import CONTAINER_KEY, HOSTNAME_KEY, INSTANCE_TYPE_KEY, K8S_OBJ_KEY


class EditFilterTag(CamelModel):
    new_filter_tag: str


class FilterTypes(str, Enum):
    CONTAINER_KEY = CONTAINER_KEY
    HOSTNAME_KEY = HOSTNAME_KEY
    K8S_OBJ_KEY = K8S_OBJ_KEY
    INSTANCE_TYPE_KEY = INSTANCE_TYPE_KEY


class RQLCompareOperators(str, Enum):
    eq_op = "$eq"
    neq_op = "$neq"
    like_op = "$like"


class RQLLogicOperators(str, Enum):
    and_op = "$and"
    or_op = "$or"


class FilterTag(CamelModel):
    name: str
    samples: Optional[str]


class RQLFilter(CamelModel):
    filter: Dict[RQLLogicOperators, List[Dict[FilterTypes, Dict[RQLCompareOperators, str]]]]

    def get_formatted_filter(self) -> str:
        res = []
        for logic_op, expressions in self.filter.items():
            for expression in expressions:
                for key, cmp_op_value in expression.items():
                    for cmp_op, value in cmp_op_value.items():
                        res.append("_".join([key, cmp_op, value]))
                res.append(logic_op)
        return "__".join(res[:-1]).replace("$", "")

    def flamedb_filter_json(self) -> bytes:
        """Serialize the filter for the query service, wrapping each ``$like`` value in
        ``%…%`` so it performs substring matching. The stored/displayed value stays raw;
        only the copy sent to flamedb gets wildcards.
        """

        def _key(item: Any) -> str:
            return item.value if isinstance(item, Enum) else str(item)

        out_filter: Dict[str, Any] = {}
        for logic_op, expressions in self.filter.items():
            new_expressions = []
            for expression in expressions:
                new_expression: Dict[str, Any] = {}
                for key, cmp_op_value in expression.items():
                    new_cmp: Dict[str, Any] = {}
                    for cmp_op, value in cmp_op_value.items():
                        if _key(cmp_op) == RQLCompareOperators.like_op.value and value and "%" not in value:
                            value = f"%{value}%"
                        new_cmp[_key(cmp_op)] = value
                    new_expression[_key(key)] = new_cmp
                new_expressions.append(new_expression)
            out_filter[_key(logic_op)] = new_expressions
        return json.dumps({"filter": out_filter}).encode()

    class Config:
        @staticmethod
        def schema_extra(schema: Dict[str, Any]) -> None:
            logic_ops_value = schema["properties"]["filter"].pop("additionalProperties")
            filter_types_value = logic_ops_value["items"].pop("additionalProperties")
            cmp_ops_value = filter_types_value.pop("additionalProperties")

            filter_types_value["properties"] = {}
            for cmp_op in RQLCompareOperators:
                filter_types_value["properties"][cmp_op] = cmp_ops_value

            logic_ops_value["items"]["properties"] = {}
            for filter_type in FilterTypes:
                logic_ops_value["items"]["properties"][filter_type] = filter_types_value

            schema["properties"]["filter"]["properties"] = {}
            for logic_op in RQLLogicOperators:
                schema["properties"]["filter"]["properties"][logic_op] = logic_ops_value


class GetRQLFilter(RQLFilter):
    id: int


class PutRQLFilter(RQLFilter):
    id: int
