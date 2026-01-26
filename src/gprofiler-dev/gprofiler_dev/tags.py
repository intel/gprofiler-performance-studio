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

import hashlib
from itertools import takewhile
from typing import Dict, List, Optional, Tuple

TagsCache = Dict[str, List[Dict]]
FilterTagList = List[Tuple[str, str, str]]
HOSTNAME_KEY = "HostName"
CONTAINER_KEY = "ContainerName"
K8S_OBJ_KEY = "ContainerEnvName"
INSTANCE_TYPE_KEY = "InstanceType"
KNOWN_SUBSERVICES = ["kube_proxy", "flink"]
BASE_16_REAL_WORDS = {
    "accede",
    "bacaba",
    "baccae",
    "beaded",
    "bedded",
    "bedead",
    "bedeaf",
    "decade",
    "deedeed",
    "deface",
    "efface",
    "fabaceae",
    "facade",
}


class FilterTags:
    def __init__(self):
        self.db = None  # not implemented

    def add(self, service: str, filter_tag: str, ui_filter: str = ""):
        # not implemented
        return None

    def list(self, service: str, just_new: bool = False):
        # not implemented
        return []

    def remove(self, service: str, filter_tag: str, ui_filter: str = ""):
        # not implemented
        return None


def get_hash_filter_tag(filter_tag):
    return hashlib.new("md5", filter_tag.encode("utf-8"), usedforsecurity=False).hexdigest()


def is_base(input_str: str, base: int) -> bool:
    try:
        int(input_str, base=base)
        return True
    except ValueError:
        return False


def should_strip(component: str) -> bool:
    # If it quacks like a duck...
    if is_base(component, 10):
        return True
    return len(component) >= 6 and is_base(component, 16) and component.lower() not in BASE_16_REAL_WORDS


def strip_pod_name(name: str):
    """
    Typical pod names are suffixed with some ID relating to the controller (ReplicaSet/DaemonSet/...)
    and pod ID, for example 'recommendationservice-d7df97cbf-5qzml'.
    In some cases, there's no suffix of the controller, only the pod ID: 'my-agent-9vnln'.

    This function does its best to filter out uniqueness identifiers and return only semantically meaningful components
    of the pod name.
    """

    for known_subservice in KNOWN_SUBSERVICES:
        if name.startswith(known_subservice):
            return known_subservice

    components = name.split("-")
    if len(components) < 2:
        return name

    new_components: List[str] = []
    for component in components:
        if should_strip(component):
            if len(new_components) == 0:
                # we don't have anything yet -- maybe the name starts with the random part
                continue
            else:
                # we have non-random components and now we see a random component.
                # assume we're done with the non-random part.
                break

        new_components.append(component)

    # If nothing was trimmed, at least remove the last part, most probably garbage
    # (In fact, pod names tend to end with a 5 char hash using the whole alphabet)
    if len(new_components) == len(components):
        del new_components[-1]

    if not new_components:
        # nothing left, I give up
        return name

    return "-".join(new_components)


def container_and_k8s_name(raw_container_name) -> Tuple[str, Optional[str]]:
    """
    Accepts a raw container name, for example: k8s_coredns_coredns-f9fd979d6-lgfsb_kube-system_d55a75f1-b1a1-4632-81c7-6107c8bfca0c_64
    For k8s, returns the (container + pod, pod) tuple:
        (coredns_coredns, coredns)
    For others, return (raw_container_name, None) -> (no K8s object name)
    TODO: keep the replicaset hash! So if there are multiple deployments of different versions, they will be listed separately.
    """
    # see parse_k8s_name() in gServer.
    if raw_container_name.startswith("k8s_"):
        parts = raw_container_name.split("_")

        try:
            _, name, sandbox_name, namespace, uid, attempt_str = parts
        except ValueError:
            # not 6 items? meh
            return raw_container_name, None

        stripped = strip_pod_name(sandbox_name)
        # these have per-node name, so we remove
        if stripped.startswith("kube-proxy-"):
            stripped = "kube-proxy"
        return f"{name}_{stripped}", f"{stripped}_{namespace}"
    elif raw_container_name.startswith("ecs-"):
        # strip the "ecs-" and "-hash"
        splitted = raw_container_name.split("-")[1:-1]
        # we strip the revision number (equivalent to stripping the replicaset hash)
        splitted_iter = iter(splitted)
        task_family = "-".join(takewhile(lambda s: not s.isdigit(), splitted_iter))
        name = "-".join(splitted_iter)  # what's left is the name
        return f"{name}_{task_family}", task_family
    return raw_container_name, None
    # TODO implement Docker swarm etc.
