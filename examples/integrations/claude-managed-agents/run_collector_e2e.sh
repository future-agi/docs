#!/usr/bin/env bash
# End-to-end run of the otelcol.yaml recipe against a self-hosted Future AGI in Docker.
#   real     the OpenTelemetry Collector container running otelcol.yaml, and the Future AGI collector and storage
#   STAND-IN Anthropic. spike/run_collector_spike.py posts payloads built from Anthropic's published span reference,
#            delivered the way Anthropic's docs describe. No Anthropic account, key, destination or session is involved,
#            so nothing here was captured from Anthropic.
# env: FI_API_KEY FI_SECRET_KEY FI_BASE_URL  PYTHON (venv with requirements.txt)  VERIFY (path to fi_verify.py, optional)
#      PROJECT [th8103-livefill-th8267]  OUT [./evidence-collector]  OTELCOL_VERSION [0.162.0]  DOCKER_HOST_ALIAS [host.docker.internal]
# Content is never printed. Starts and removes only its own container (th8103-rest-cma-otelcol).
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"; OUT="${OUT:-$PWD/evidence-collector}"; P="${PROJECT:-th8103-livefill-th8267}"
V="${OTELCOL_VERSION:-0.162.0}"; PORT=14267; CNAME=th8103-rest-cma-otelcol
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}"
FI_URL="${FI_BASE_URL/localhost/${DOCKER_HOST_ALIAS:-host.docker.internal}}"; FI_URL="${FI_URL/127.0.0.1/${DOCKER_HOST_ALIAS:-host.docker.internal}}"
export ANTHROPIC_DEST_TOKEN="ant-$("$PY" -c 'import secrets; print(secrets.token_hex(16))')"
mkdir -p "$OUT"; S="$OUT/summary.txt"; : > "$S"; FAILED=0
trap 'docker rm -f $CNAME >/dev/null 2>&1' EXIT
uid() { "$PY" -c 'import secrets; print(secrets.token_hex(5).upper())'; }
start() { # project capture
  docker rm -f $CNAME >/dev/null 2>&1; while docker inspect $CNAME >/dev/null 2>&1; do sleep 1; done
  docker run -d --name $CNAME --memory 512m -p 127.0.0.1:$PORT:4318 -v "$HERE/otelcol.yaml:/etc/otelcol/config.yaml:ro" \
    -e ANTHROPIC_DEST_TOKEN -e FI_API_KEY -e FI_SECRET_KEY -e FI_PROJECT_NAME="$1" -e FI_CAPTURE_CONTENT="$2" \
    -e FI_TRACES_URL="$FI_URL/v1/traces" "otel/opentelemetry-collector-contrib:$V" --config /etc/otelcol/config.yaml >/dev/null || { echo "collector did not start"; exit 1; }
  for _ in $(seq 60); do curl -s -o /dev/null -X POST -H "Authorization: Bearer $ANTHROPIC_DEST_TOKEN" -H 'Content-Type: application/x-protobuf' "http://127.0.0.1:$PORT/v1/traces" && return; sleep 1; done
  docker logs $CNAME 2>&1 | tail -5; echo "collector not ready"; exit 1
}
send() { # scenario marker out
  MARKER="$2" "$PY" -I "$HERE/spike/run_collector_spike.py" "http://127.0.0.1:$PORT/v1/traces" "$1" "$OUT/$3.json" | tee -a "$S"
}
verify() { # project min extra...
  local p="$1" n="$2"; shift 2
  [ -z "${VERIFY:-}" ] && { echo "fi_verify skipped" | tee -a "$S"; return; }
  "$PY" "$VERIFY" --project "$p" --wait 240 --min-spans "$n" --json "$OUT/spans-$p.json" "$@" > "$OUT/verify-$p.txt" 2>&1
  if grep -q '^PASS' "$OUT/verify-$p.txt"; then echo "fi_verify PASS $p" | tee -a "$S"; else echo "fi_verify FAIL $p" | tee -a "$S"; FAILED=1; fi
  sed -n '1,30p' "$OUT/verify-$p.txt" | cut -c1-200
}
M1="CMAA$(uid)"; M2="CMAB$(uid)"; M3="CMAC$(uid)"; M4="CMAD$(uid)"
echo "markers: $M1 $M2 $M3 $M4" > "$OUT/markers-private.txt"

echo "== content OFF (default), project $P-meta"; start "$P-meta" false
send badtoken "$M1" run-badtoken
send metadata "$M1" run-metadata
send content "$M2" run-content-in-off-collector
send error "$M3" run-error
send duplicate "$M4" run-duplicate
sleep 8; docker logs $CNAME > "$OUT/collector-off.log" 2>&1
verify "$P-meta" 14
echo "== content ON, project $P-full"; M5="CMAE$(uid)"; echo "$M5" >> "$OUT/markers-private.txt"; start "$P-full" true
send content "$M5" run-content-on
sleep 8; docker logs $CNAME > "$OUT/collector-on.log" 2>&1
verify "$P-full" 5
echo "$FAILED" > "$OUT/failed.txt"; echo "done; failed=$FAILED"
