#!/usr/bin/env bash
# Re-capture fixtures/*.pb from a real Gravitee Gateway. The Gateway exports to capture_server.py (a local
# sink) instead of a collector, so these are exactly the bytes Gravitee puts on the wire. No keys needed.
#   gravitee-<v>-extra-attributes.pb  extraAttributes [project_name, project_type] set in gravitee.yml
#   gravitee-<v>-content-off.pb       the shipped gravitee-opentelemetry.yml, POST /fi-echo
#   gravitee-<v>-backend-down.pb      the shipped config, GET /fi-down (backend unreachable)
#   gravitee-<v>-verbose.pb           the opt-in: verbose on the Gateway and on the API, POST /fi-echo-verbose
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SINK_PORT="${SINK_PORT:-18318}"
CAP="$EVID/capture"; rm -rf "$CAP"; mkdir -p "$CAP"
"$PY" "$HERE/echo_server.py" --port "$BACKEND_PORT" --log "$EVID/capture-backend.log" & BACKEND_PID=$!
trap 'kill "$BACKEND_PID" "${SINK_PID:-}" 2>/dev/null || true; cleanup_all' EXIT
docker rm -f "$PREFIX-mongo" >/dev/null 2>&1 || true
start_mongo; start_mapi
"$PY" "$HERE/create_apis.py" --mapi "http://127.0.0.1:$MAPI_PORT" --backend "http://host.docker.internal:$BACKEND_PORT"
stop_mapi
export gravitee_services_opentelemetry_exporter_endpoint="http://host.docker.internal:$SINK_PORT"
export gravitee_services_opentelemetry_exporter_headers_0_name=Authorization
export gravitee_services_opentelemetry_exporter_headers_0_value="Bearer capture-only-token"
req() {  # req <method> <api> [json body]: markers in body, query string and headers
  curl -s -o /dev/null -w "$2 %{http_code}\n" -X "$1" "http://127.0.0.1:$GW_PORT/$2/orders?q=CAPMARK-query&email=someone@example.com" \
    -H "traceparent: 00-$(hex32)-$(hex16)-01" -H "Authorization: Bearer CAPMARK-auth" -H "X-Custom: CAPMARK-hdr" \
    -H "Cookie: session=CAPMARK-cookie" -H "X-Gravitee-Api-Key: CAPMARK-apikey" -H 'content-type: application/json' \
    ${3:+-d "$3"}
}
hex32() { "$PY" -c 'import uuid;print(uuid.uuid4().hex)'; }
hex16() { "$PY" -c 'import uuid;print(uuid.uuid4().hex[:16])'; }
# phase <name> [render args]: start a sink and a Gateway rendered with the shipped config (+ args)
phase() {
  local name="$1"; shift
  mkdir -p "$CAP/$name"
  "$PY" "$HERE/capture_server.py" --port "$SINK_PORT" --out-dir "$CAP/$name" & SINK_PID=$!
  render "$EVID/gw.capture.$name.yml" "$@"
  start_gateway "$EVID/gw.capture.$name.yml"
}
end_phase() { sleep 8; stop_gateway; rm_gateway; kill "$SINK_PID" 2>/dev/null || true; wait "$SINK_PID" 2>/dev/null || true; }

phase extra --extra-attr project_name=my-gravitee-project --extra-attr project_type=observe
req POST fi-echo '{"prompt":"CAPMARK-body"}'; end_phase
phase off
req POST fi-echo '{"prompt":"CAPMARK-body someone@example.com"}'; req GET fi-down; end_phase
export gravitee_services_opentelemetry_verbose=true
phase verbose
req POST fi-echo-verbose '{"prompt":"CAPMARK-body"}'; end_phase
unset gravitee_services_opentelemetry_verbose

V="$GRAVITEE_VERSION"
"$PY" - "$CAP" "$HERE/fixtures" "$V" <<'EOF'
import pathlib, sys
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
cap, out, v = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
want = {("extra", "fi-echo"): "extra-attributes", ("off", "fi-echo"): "content-off",
        ("off", "fi-down"): "backend-down", ("verbose", "fi-echo-verbose"): "verbose"}
out.mkdir(exist_ok=True)
for (phase, api), label in want.items():
    merged = ExportTraceServiceRequest()
    for f in sorted((cap / phase).glob("*.bin")):
        r = ExportTraceServiceRequest(); r.ParseFromString(f.read_bytes())
        for rs in r.resource_spans:
            if any(a.key == "gravitee.api.name" and a.value.string_value == api for a in rs.resource.attributes):
                merged.resource_spans.append(rs)
    assert merged.resource_spans, f"nothing captured for {phase}/{api}"
    (out / f"gravitee-{v}-{label}.pb").write_bytes(merged.SerializeToString())
    print("wrote", f"gravitee-{v}-{label}.pb", len(merged.resource_spans[0].scope_spans), "scopes")
EOF
