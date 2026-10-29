#!/usr/bin/env python3
"""Create and deploy the v4 HTTP proxy APIs used by run_e2e.sh, through the real
Gravitee Management API v2 (the same calls the Console makes).

Each API gets a Keyless plan, one request flow with a Transform Headers policy
(so there is a policy span; verbose tracing attaches its span events to policy
spans), and the per-API tracing switch the page describes:
`analytics.tracing.enabled` (Console: API > Reporter settings > OpenTelemetry >
Trace enabled) and, for one API, `analytics.tracing.verbose`.

  create_apis.py --mapi http://127.0.0.1:18083 --backend http://host.docker.internal:18090/
"""
import argparse
import json
import sys
import time

import requests

ap = argparse.ArgumentParser()
ap.add_argument("--mapi", default="http://127.0.0.1:18083")
ap.add_argument("--user", default="admin")
ap.add_argument("--password", default="admin")
ap.add_argument("--backend", required=True, help="echo backend as seen from the Gateway container")
ap.add_argument("--llm-backend", default="", help="optional OpenAI-compatible base URL, proxied at /fi-llm/")
a = ap.parse_args()
BASE = f"{a.mapi}/management/v2/organizations/DEFAULT/environments/DEFAULT"
S = requests.Session()
S.auth = (a.user, a.password)
S.headers["Content-Type"] = "application/json"

# name, context path, backend target, tracing enabled, verbose
APIS = [
    ("fi-echo", "/fi-echo/", a.backend, True, False),          # content off (verbose false)
    ("fi-echo-verbose", "/fi-echo-verbose/", a.backend, True, True),   # the opt-in
    ("fi-down", "/fi-down/", "http://host.docker.internal:1/", True, False),  # failure case
    ("fi-untraced", "/fi-untraced/", a.backend, False, False),  # per-API switch off
]
if a.llm_backend:
    APIS.append(("fi-llm", "/fi-llm/", a.llm_backend, True, False))


def call(method, path, body=None, ok=(200, 201, 202, 204)):
    r = S.request(method, BASE + path, data=json.dumps(body) if body is not None else None, timeout=60)
    if r.status_code not in ok:
        sys.exit(f"{method} {path} -> {r.status_code} {r.text[:400]}")
    return r.json() if r.text else {}


existing = {x["name"]: x["id"] for x in call("GET", "/apis?perPage=100").get("data", [])}
out = {}
for name, path, target, tracing, verbose in APIS:
    if name in existing:
        out[name] = existing[name]
        continue
    api = call("POST", "/apis", {
        "name": name, "apiVersion": "1.0", "definitionVersion": "V4", "type": "PROXY",
        "description": "Future AGI OpenTelemetry recipe test API",
        "listeners": [{"type": "HTTP", "paths": [{"path": path}],
                       "entrypoints": [{"type": "http-proxy", "qos": "AUTO"}]}],
        "endpointGroups": [{"name": "backend-group", "type": "http-proxy",
                            "endpoints": [{"name": "backend", "type": "http-proxy", "weight": 1,
                                           "inheritConfiguration": False,
                                           "configuration": {"target": target}}]}],
        "analytics": {"enabled": True, "tracing": {"enabled": tracing, "verbose": verbose}},
        "flows": [{
            "name": "add-recipe-header", "enabled": True,
            "selectors": [{"type": "HTTP", "path": "/", "pathOperator": "STARTS_WITH", "methods": []}],
            "request": [{
                "name": "Transform Headers", "description": "Tag the backend request", "enabled": True,
                "policy": "transform-headers",
                "configuration": {"addHeaders": [{"name": "X-Fi-Recipe", "value": "gravitee-otel"}]},
            }],
            "response": [], "subscribe": [], "publish": [],
        }],
    })
    plan = call("POST", f"/apis/{api['id']}/plans", {
        "definitionVersion": "V4", "name": "Keyless", "description": "no auth",
        "security": {"type": "KEY_LESS"}, "validation": "AUTO", "mode": "STANDARD",
    })
    call("POST", f"/apis/{api['id']}/plans/{plan['id']}/_publish")
    call("POST", f"/apis/{api['id']}/_start")
    call("POST", f"/apis/{api['id']}/deployments", {"deploymentLabel": "fi-otel-recipe"})
    out[name] = api["id"]
for name, api_id in out.items():
    tr = call("GET", f"/apis/{api_id}").get("analytics", {}).get("tracing", {})
    print(f"{name}: id={api_id} tracing={tr}")
