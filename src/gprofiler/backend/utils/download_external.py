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
from dataclasses import dataclass
from logging import getLogger
from typing import Dict, Optional, Tuple

import jsonschema
import requests
import yaml
from backend.models.installation_models import FileType
from gprofiler_dev import config

GH_RELEASES_API = "https://api.github.com/repos/intel/gprofiler/releases/latest"
DAEMON_SET_URL = "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/k8s/gprofiler.yaml"
ECS_URL = "https://raw.githubusercontent.com/intel/gprofiler/blob/master/deploy/ecs/gprofiler_task_definition.json"
ANSIBLE_URL = "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/ansible/gprofiler_playbook.yml"
DOCKER_COMPOSE_URL = "https://raw.githubusercontent.com/intel/gprofiler/master/deploy/docker-compose/docker-compose.yml"
GH_PUBLISH_DATE_REQUEST_TIMEOUT = 30

FILE_URLS = {
    FileType.ecs: {"file_url": ECS_URL, "fallback_path": "backend/utils/ecs_files/task_definition.json"},
    FileType.ansible: {"file_url": ANSIBLE_URL, "fallback_path": "backend/utils/ansible_files/gprofiler_playbook.yml"},
    FileType.docker_compose: {
        "file_url": DOCKER_COMPOSE_URL,
        "fallback_path": "backend/utils/docker_compose_files/docker-compose.yml",
    },
}


@dataclass
class DaemonSetConfig:
    namespace: Dict
    gprofiler: Dict


# gProfiler latest release date
_DAEMON_SET_CACHE: Optional[str] = None
_ECS_CACHE: Optional[str] = None
_FILE_CACHE: Optional[str] = None
_GPROFILER_LATEST_RELEASE_DATE: str = ""

logger = getLogger(__name__)


def _download_or_fallback(url: str, fallback_path: str) -> str:
    try:
        res = requests.get(url, timeout=5)
    except Exception:
        logger.exception(f"Failed to download {url}\n")
    else:
        if res.ok:
            return res.text

        logger.warning(
            f"Failed to download {url}\n" f"response code: {res.status_code}\n" f"msg: {res.text}\nUsing fallback file"
        )

    with open(fallback_path, "r") as file_input:
        return file_input.read()


def get_daemon_set_template(token: str, service_name: str) -> DaemonSetConfig:
    return get_k8s_template(token, service_name)


def get_k8s_template(token: str, service_name: str) -> DaemonSetConfig:
    global _GPROFILER_LATEST_RELEASE_DATE
    global _DAEMON_SET_CACHE
    daemon_set_template, publish_date = _get_raw_daemon_set_template(_DAEMON_SET_CACHE, _GPROFILER_LATEST_RELEASE_DATE)
    try:
        # The '@' is used in the gProfiler template to require parameters (the k8s will reject illegal YAMLs until the
        # user changes those values to valid parameters)
        daemon_set = daemon_set_template.replace("@insert your token here@", token).replace(
            "@insert service name here@", service_name
        )

        namespace_config, gprofiler_config = yaml.safe_load_all(daemon_set)
        gprofiler_config["spec"]["template"]["spec"]["containers"][0]["env"].append(
            {"name": "GPROFILER_SERVER_HOST", "value": config.REDIRECT_DOMAIN}
        )
        daemon_set_config = DaemonSetConfig(namespace=namespace_config, gprofiler=gprofiler_config)

        with open("backend/utils/daemonset_files/daemonsetspec.json", "r") as file_in:
            schema = file_in.read()
        schema_file = json.loads(schema)
        jsonschema.validate(instance=daemon_set_config.gprofiler["spec"], schema=schema_file)
        _DAEMON_SET_CACHE = daemon_set_template

        with open("backend/utils/daemonset_files/daemonset.yml", "w") as file_output:
            file_output.write(daemon_set_template)
        if publish_date is not None:
            _GPROFILER_LATEST_RELEASE_DATE = publish_date
        return daemon_set_config
    except Exception:
        logger.exception("Error while parse and validate DaemonSet file")
        raise


def get_template(file_type: FileType, replacements_dict: dict) -> str:
    global _GPROFILER_LATEST_RELEASE_DATE
    global _FILE_CACHE
    file_template, publish_date = _get_raw_template(
        _ECS_CACHE,
        _GPROFILER_LATEST_RELEASE_DATE,
        FILE_URLS[file_type]["file_url"],
        FILE_URLS[file_type]["fallback_path"],
    )

    installation_file = file_template
    for key in replacements_dict:
        installation_file = installation_file.replace(key, replacements_dict[key])

    _FILE_CACHE = file_template
    with open(FILE_URLS[file_type]["fallback_path"], "w") as file_output:
        file_output.write(installation_file)
    if publish_date is not None:
        _GPROFILER_LATEST_RELEASE_DATE = publish_date
    return installation_file


def _get_raw_daemon_set_template(
    cached_daemon_set_template, latest_gprofiler_release_date
) -> Tuple[str, Optional[str]]:
    res = requests.get(GH_RELEASES_API, timeout=GH_PUBLISH_DATE_REQUEST_TIMEOUT)
    publish_date = latest_gprofiler_release_date
    if res.ok:
        agent_publish_date = res.json()["published_at"]
        if agent_publish_date > publish_date:
            publish_date = agent_publish_date
            return _download_or_fallback(DAEMON_SET_URL, "backend/utils/daemonset_files/daemonset.yml"), publish_date
    elif cached_daemon_set_template is None:
        return _download_or_fallback(DAEMON_SET_URL, "backend/utils/daemonset_files/daemonset.yml"), None
    return cached_daemon_set_template, publish_date


def _get_raw_template(
    cached_template, latest_gprofiler_release_date, file_url: str, fallback_path: str
) -> Tuple[str, Optional[str]]:
    res = requests.get(GH_RELEASES_API, timeout=GH_PUBLISH_DATE_REQUEST_TIMEOUT)
    publish_date = latest_gprofiler_release_date
    if res.ok:
        agent_publish_date = res.json()["published_at"]
        if agent_publish_date > publish_date or not cached_template:
            publish_date = agent_publish_date
            return _download_or_fallback(file_url, fallback_path), publish_date
    elif cached_template is None:
        return _download_or_fallback(file_url, fallback_path), None
    return cached_template, publish_date
