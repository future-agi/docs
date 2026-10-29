#!/usr/bin/env bash
# End-to-end check of the Swiftide recipe against a real Future AGI (self-hosted) and a real
# OpenAI-compatible model endpoint.
#
#   ./run_e2e.sh [main|privacy|no-shutdown|exporter-down|matrix|all]
#
# Required env: FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL (your Future AGI, e.g. http://localhost:<port>),
#               OPENAI_API_KEY, OPENAI_BASE_URL (optional for api.openai.com), MODEL.
# Optional env: FI_PROJECT_PREFIX (default swiftide-e2e), RUN_ID (default: time stamp),
#               PYTHON (needs opentelemetry-proto + protobuf, for the wire tap),
#               VERIFY (path to a fi_verify.py that reads the stack's database; skipped if unset),
#               EVIDENCE (output dir, default ./evidence), TAP_PORT (default 14551),
#               MATRIX_VERSIONS (default "0.32.1"), CARGO_TARGET_DIR.
#
# Every run goes through tools/wire_tap.py, which forwards to FI_BASE_URL and records what was
# really sent (header names, never values). The privacy scenario also needs `docker exec` access
# to the stack's Postgres and ClickHouse containers (FI_PG_CONTAINER, FI_CH_CONTAINER).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCENARIO="${1:-all}"
: "${FI_API_KEY:?}" "${FI_SECRET_KEY:?}" "${FI_BASE_URL:?}" "${OPENAI_API_KEY:?}" "${MODEL:?}"
PREFIX="${FI_PROJECT_PREFIX:-swiftide-e2e}"
RUN_ID="${RUN_ID:-$(date +%H%M%S)}"
PY="${PYTHON:-python3}"
EVIDENCE="${EVIDENCE:-$HERE/evidence}"
TAP_PORT="${TAP_PORT:-14551}"
TARGET="${CARGO_TARGET_DIR:-$HERE/target}"
P="$PREFIX-$RUN_ID"
mkdir -p "$EVIDENCE"
FAILED=()

log() { printf '\n=== %s\n' "$*"; }
fail() { echo "FAIL: $*"; FAILED+=("$*"); }

TAP_PID=""
start_tap() { # $1 = capture file, $2 = forward URL
  stop_tap
  : >"$1"
  TAP_EXPECT_API_KEY="$FI_API_KEY" TAP_EXPECT_SECRET_KEY="$FI_SECRET_KEY" \
    "$PY" -I "$HERE/tools/wire_tap.py" --listen "$TAP_PORT" --out "$1" --forward "$2" 2>/dev/null &
  TAP_PID=$!
  for _ in $(seq 1 50); do
    curl -s -o /dev/null "http://127.0.0.1:$TAP_PORT/" && return 0
    sleep 0.1
  done
  echo "wire tap did not start"; return 1
}
stop_tap() { [ -n "$TAP_PID" ] && kill "$TAP_PID" 2>/dev/null; wait "$TAP_PID" 2>/dev/null; TAP_PID=""; }
trap stop_tap EXIT

build() { # $1 = crate dir
  (cd "$1" && CARGO_TARGET_DIR="$TARGET/$(basename "$1")" cargo build --locked --quiet) || return 1
  BIN="$TARGET/$(basename "$1")/debug/swiftide-futureagi-tracing"
}

agent() { # $1 = project, $2 = question, rest = extra env (KEY=VALUE)
  local project="$1" question="$2"; shift 2
  env FI_BASE_URL="http://127.0.0.1:$TAP_PORT" FI_PROJECT_NAME="$project" RUST_LOG="${RUST_LOG:-warn}" \
    "$@" "$BIN" "$question"
}

verify() { # $1 = project, $2 = min spans, $3 = json out. Retries: a busy ClickHouse can refuse reads.
  [ -n "${VERIFY:-}" ] || { echo "(VERIFY not set: skipping the database read-back)"; return 0; }
  local i
  for i in 1 2 3 4 5 6; do
    "$PY" "$VERIFY" --project "$1" --wait 120 --min-spans "$2" --json "$3" && return 0
    echo "(read-back attempt $i failed; retrying in 30 s)"; sleep 30
  done
  return 1
}

scenario_main() { # $1 = crate dir, $2 = project
  log "main: answer + tool error + model error -> $2"
  build "$1" || { fail "build $1"; return; }
  local wire="$EVIDENCE/$2.wire.jsonl"
  start_tap "$wire" "$FI_BASE_URL" || { fail tap; return; }
  agent "$2" "What is the weather in Paris right now?" MODEL="$MODEL" || fail "$2: answer run exited non-zero"
  agent "$2" "What is the weather in Atlantis? Call the weather tool exactly once. If it fails, say so and stop." MODEL="$MODEL" \
    || fail "$2: tool-error run exited non-zero"
  if agent "$2" "What is the weather in Paris?" MODEL="no-such-model-$RUN_ID"; then fail "$2: model-error run should exit 1"; fi
  stop_tap
  "$PY" "$HERE/tools/wire_summary.py" "$wire" --project "$2" || fail "$2: wire summary"
  if [ -n "${VERIFY:-}" ]; then
    verify "$2" 14 "$EVIDENCE/$2.spans.json" || fail "$2: fi_verify"
    "$PY" "$HERE/tools/check_trace.py" "$EVIDENCE/$2.spans.json" --traces 3 --ok 1 --model-errors 1 --tool-errors 1 \
      || fail "$2: check_trace"
  fi
}

privacy_runs() { # $1 = project, $2 = marker, rest = extra env
  local project="$1" marker="$2"; shift 2
  agent "$project" "$marker asks: what is the weather in Lisbon? Reply with the tool result." MODEL="$MODEL" \
    RUST_BACKTRACE=1 RUST_LIB_BACKTRACE=1 "$@" || fail "$project: answer run"
  agent "$project" "What is the weather in Atlantis-$marker? Call the weather tool exactly once. If it fails, stop." \
    MODEL="$MODEL" RUST_BACKTRACE=1 RUST_LIB_BACKTRACE=1 "$@" || fail "$project: tool-error run"
  agent "$project" "What is the weather in Paris?" MODEL="nomodel-$marker" RUST_BACKTRACE=1 RUST_LIB_BACKTRACE=1 "$@" \
    && fail "$project: model-error run should exit 1"
  return 0
}

scenario_privacy() {
  build "$HERE" || { fail build; return; }
  local off="$P-content-off" on="$P-content-on"
  local m_off="PRIVOFF$RUN_ID$RANDOM" m_on="PRIVON$RUN_ID$RANDOM"
  local needles=(
    "user=$(id -un)" "host=$(hostname -s)" "home=$HOME" "cwd=$PWD" "backtrace=Stack backtrace"
    "registry=registry/src" "fi_api_key=$FI_API_KEY" "fi_secret_key=$FI_SECRET_KEY" "model_key=$OPENAI_API_KEY"
  )
  local args=() n
  for n in "${needles[@]}"; do args+=(--needle "$n"); done

  log "privacy: content OFF (default) -> $off"
  start_tap "$EVIDENCE/$off.wire.jsonl" "$FI_BASE_URL" || { fail tap; return; }
  privacy_runs "$off" "$m_off"
  stop_tap
  "$PY" "$HERE/tools/wire_summary.py" "$EVIDENCE/$off.wire.jsonl" --project "$off" || fail "$off: wire summary"
  verify "$off" 10 "$EVIDENCE/$off.spans.json" || fail "$off: fi_verify"
  "$PY" "$HERE/tools/scan_local_stack.py" --project "$off" --wire "$EVIDENCE/$off.wire.jsonl" \
    --needle "marker=$m_off" "${args[@]}" --json "$EVIDENCE/$off.scan.json" || fail "$off: privacy scan"

  log "privacy: content ON (TRACE_CONTENT=true) -> $on"
  start_tap "$EVIDENCE/$on.wire.jsonl" "$FI_BASE_URL" || { fail tap; return; }
  privacy_runs "$on" "$m_on" TRACE_CONTENT=true
  stop_tap
  verify "$on" 10 "$EVIDENCE/$on.spans.json" || fail "$on: fi_verify"
  "$PY" "$HERE/tools/scan_local_stack.py" --project "$on" --needle "marker=$m_on" --expect-found \
    --json "$EVIDENCE/$on.scan-marker.json" || fail "$on: opt-in marker not stored"
  "$PY" "$HERE/tools/scan_local_stack.py" --project "$on" --wire "$EVIDENCE/$on.wire.jsonl" "${args[@]}" \
    --json "$EVIDENCE/$on.scan.json" || fail "$on: never-exported strings found with content on"

  log "tenant isolation (whole spans table)"
  "$PY" "$HERE/tools/isolation_check.py" --needle "$m_on" --only "$on" || fail "isolation: opt-in marker"
  "$PY" "$HERE/tools/isolation_check.py" --needle "$m_off" --nowhere || fail "isolation: content-off marker"
}

scenario_no_shutdown() {
  build "$HERE" || { fail build; return; }
  local project="$P-no-shutdown" wire="$EVIDENCE/$P-no-shutdown.wire.jsonl"
  log "no-shutdown (PRD AC-05): SKIP_SHUTDOWN=1 -> $project"
  start_tap "$wire" "$FI_BASE_URL" || { fail tap; return; }
  agent "$project" "What is the weather in Tokyo?" MODEL="$MODEL" SKIP_SHUTDOWN=1 || fail "$project: run"
  sleep 3; stop_tap
  if grep -q '"agent.query"' "$wire"; then fail "$project: agent.query was exported without shutdown"; else
    echo "PASS  no-shutdown: $(wc -l <"$wire" | tr -d ' ') request(s) reached the tap; the root agent.query span never did"; fi
}

scenario_exporter_down() {
  build "$HERE" || { fail build; return; }
  log "exporter-down (PRD J5): nothing listens on the Future AGI URL"
  local out="$EVIDENCE/$P-exporter-down.log"
  if env FI_BASE_URL="http://127.0.0.1:9" FI_PROJECT_NAME="$P-exporter-down" MODEL="$MODEL" RUST_LOG=warn \
    "$BIN" "What is the weather in Tokyo?" >"$out" 2>&1; then
    echo "PASS  agent answered (exit 0) with the exporter failing:"; grep -E "telemetry data will be lost|ExportError" "$out" | sed 's/\x1b\[[0-9;]*m//g' | head -3
  else fail "exporter-down: agent exited non-zero"; fi
}

scenario_matrix() {
  local v dir
  for v in ${MATRIX_VERSIONS:-0.32.1}; do
    dir="$TARGET/matrix-src/swiftide-$v"
    rm -rf "$dir"; mkdir -p "$dir"
    cp -R "$HERE/src" "$dir/"
    # Same crate with another swiftide pin; dev-dependencies dropped (only the binary is built).
    local edits=(-e "s/swiftide = { version = \"=[0-9.]*\"/swiftide = { version = \"=$v\"/" -e '/^\[dev-dependencies\]/,$d')
    # swiftide 0.32.x was released against async-openai 0.30.1 (its own v0.32.1 Cargo.lock).
    case "$v" in 0.32.*) edits+=(-e 's/async-openai = { version = "=[0-9.]*"/async-openai = { version = "=0.30.1"/') ;; esac
    sed "${edits[@]}" "$HERE/Cargo.toml" >"$dir/Cargo.toml"
    (cd "$dir" && cargo generate-lockfile --quiet) || { fail "matrix $v: lockfile"; continue; }
    case "$v" in
      # swiftide 0.32.x asks for async-openai ">=0.29.6", which now resolves to an incompatible
      # 0.42.x for swiftide itself and does not compile. Move it to 0.30.1 too.
      0.32.*)
        local newest
        newest=$(awk '/^name = "async-openai"$/{getline; gsub(/"/, "", $3); print $3}' "$dir/Cargo.lock" | sort -V | tail -1)
        (cd "$dir" && cargo update --quiet -p "async-openai@$newest" --precise 0.30.1) || { fail "matrix $v: pin"; continue; } ;;
    esac
    scenario_main "$dir" "$P-swiftide-$v"
  done
}

case "$SCENARIO" in
  main) scenario_main "$HERE" "$P" ;;
  privacy) scenario_privacy ;;
  no-shutdown) scenario_no_shutdown ;;
  exporter-down) scenario_exporter_down ;;
  matrix) scenario_matrix ;;
  all) scenario_main "$HERE" "$P"; scenario_privacy; scenario_no_shutdown; scenario_exporter_down; scenario_matrix ;;
  *) echo "unknown scenario $SCENARIO"; exit 2 ;;
esac

echo
if [ ${#FAILED[@]} -eq 0 ]; then echo "E2E RESULT: PASS ($SCENARIO, projects $P*)"; else
  echo "E2E RESULT: FAIL"; printf ' - %s\n' "${FAILED[@]}"; exit 1; fi
