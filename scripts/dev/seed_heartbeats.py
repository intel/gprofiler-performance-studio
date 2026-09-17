#!/usr/bin/env python3
"""Local dev helper: send synthetic agent heartbeats to the Performance Studio.

This populates HostHeartbeats so the Adhoc Profile Configuration page
(/profiling) shows data across the Services / Namespaces / Hosts / Pods /
Containers / Processes tabs. The workload_status API only returns hosts whose
heartbeat_timestamp is within the last 2 minutes, so this script loops and
re-sends heartbeats on an interval to keep the fleet "live".

Usage:
    python3 seed_heartbeats.py                # loop forever (default 45s)
    python3 seed_heartbeats.py --once         # send a single round and exit
    python3 seed_heartbeats.py --interval 30  # custom loop interval (seconds)

Env / flags:
    --base-url   default https://localhost:4433
    --user/--password  basic-auth creds (default user/admin)
"""
import argparse
import json
import ssl
import sys
import time
import urllib.request
from datetime import datetime, timezone

# Synthetic fleet: service -> list of host specs.
# Each container carries a namespace/pod/workload plus a few processes so that
# every scope tab (service/namespace/host/pod/container/process) has rows.
RUNTIMES = {
    "java": "java -Xmx4g -jar app.jar",
    "python": "python3 /srv/app/server.py",
    "node": "node dist/server.js",
    "nginx": "nginx: master process",
    "envoy": "/usr/local/bin/envoy -c /etc/envoy/envoy.yaml",
    "go": "/srv/bin/service",
}

FLEET = [
    {
        "service": "ingress-webapp-canary-use1",
        "namespace": "canary",
        "agent_version": "1.53.1",
        "hosts": [
            {"host": "ip-10-0-1-245", "ip": "10.0.1.245",
             "containers": [
                 {"name": "webapp-nginx", "pod": "ingress-webapp-canary-a4b1", "kind": "Deployment",
                  "procs": [("nginx", 7891), ("node", 9156)]},
             ]},
            {"host": "ip-10-0-2-156", "ip": "10.0.2.156",
             "containers": [
                 {"name": "webapp-api", "pod": "ingress-webapp-canary-77cd", "kind": "Deployment",
                  "procs": [("java", 8234), ("python", 8412)]},
             ]},
            {"host": "ip-10-0-3-089", "ip": "10.0.3.089",
             "containers": [
                 {"name": "webapp-worker", "pod": "ingress-webapp-canary-2f0a", "kind": "Deployment",
                  "procs": [("python", 9001)]},
             ]},
        ],
    },
    {
        "service": "homefeed",
        "namespace": "production",
        "agent_version": "1.53.1",
        "hosts": [
            {"host": "ip-10-1-4-234", "ip": "10.1.4.234",
             "containers": [
                 {"name": "homefeed-app", "pod": "unity-homefeed-docker-prod-7d8f", "kind": "StatefulSet",
                  "procs": [("node", 9156), ("go", 9210)]},
             ]},
            {"host": "ip-10-1-5-101", "ip": "10.1.5.101",
             "containers": [
                 {"name": "homefeed-ranker", "pod": "unity-homefeed-docker-prod-9911", "kind": "StatefulSet",
                  "procs": [("java", 8801)]},
             ]},
        ],
    },
    {
        "service": "unity-p2p",
        "namespace": "production",
        "agent_version": "1.53.1",
        "hosts": [
            {"host": "ip-10-1-6-12", "ip": "10.1.6.12",
             "containers": [
                 {"name": "unity-p2p-main", "pod": "unity-p2p-docker-prod-7d8f", "kind": "Deployment",
                  "procs": [("java", 8234)]},
                 {"name": "unity-p2p-sidecar", "pod": "unity-p2p-docker-prod-7d8f", "kind": "Deployment",
                  "procs": [("envoy", 8421)]},
             ]},
        ],
    },
    {
        "service": "ingress-trk-canary-use1",
        "namespace": "staging",
        "agent_version": "1.53.1",
        "hosts": [
            {"host": "ip-10-2-7-55", "ip": "10.2.7.55",
             "containers": [
                 {"name": "trk-collector", "pod": "ingress-trk-staging-1a2b", "kind": "DaemonSet",
                  "procs": [("go", 7001)]},
             ]},
        ],
    },
    {
        "service": "ingress-widgets-canary-use1",
        "namespace": "development",
        "agent_version": "1.53.1",
        "hosts": [
            {"host": "ip-10-3-8-77", "ip": "10.3.8.77",
             "containers": [
                 {"name": "widgets-web", "pod": "ingress-widgets-dev-9f2c", "kind": "Deployment",
                  "procs": [("python", 6001), ("nginx", 6010)]},
             ]},
        ],
    },
]


def build_heartbeats():
    rounds = []
    for svc in FLEET:
        for host in svc["hosts"]:
            containers = []
            for c in host["containers"]:
                containers.append({
                    "containerId": f"{c['name']}-{host['host']}",
                    "containerName": c["name"],
                    "runtime": "containerd",
                    "namespace": svc["namespace"],
                    "podName": c["pod"],
                    "workloadName": c["pod"].rsplit("-", 1)[0],
                    "workloadKind": c["kind"],
                    "processes": [
                        {"pid": pid, "processName": RUNTIMES.get(rt, rt)}
                        for (rt, pid) in c["procs"]
                    ],
                })
            rounds.append({
                "ip_address": host["ip"],
                "hostname": host["host"],
                "service_name": svc["service"],
                "agent_version": svc["agent_version"],
                "run_mode": "container",
                "namespace": svc["namespace"],
                "pod_name": host["containers"][0]["pod"],
                "containers": containers,
                "status": "active",
                # Agent-normalized PMU event names (UI 'cpu-cycles' -> 'cycles')
                "perf_supported_events": [
                    "cycles", "instructions", "cache-misses", "cache-references",
                    "branch-instructions", "branch-misses",
                ],
            })
    return rounds


def send(base_url, user, password, payloads):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    mgr.add_password(None, base_url, user, password)
    opener = urllib.request.build_opener(
        urllib.request.HTTPBasicAuthHandler(mgr),
        urllib.request.HTTPSHandler(context=ctx),
    )
    ok = 0
    for hb in payloads:
        hb["timestamp"] = datetime.now(timezone.utc).isoformat()
        data = json.dumps(hb).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/metrics/heartbeat", data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with opener.open(req, timeout=10) as resp:
                if resp.status == 200:
                    ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  heartbeat failed for {hb['hostname']}: {e}", file=sys.stderr)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://localhost:4433")
    ap.add_argument("--user", default="user")
    ap.add_argument("--password", default="admin")
    ap.add_argument("--interval", type=int, default=45)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    payloads = build_heartbeats()
    print(f"Seeding {len(payloads)} hosts across {len(FLEET)} services to {args.base_url}")
    while True:
        ok = send(args.base_url, args.user, args.password, payloads)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] sent {ok}/{len(payloads)} heartbeats")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
