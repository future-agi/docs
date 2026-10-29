#!/usr/bin/env bash
# End-to-end run of the Temporal recipe against a Future AGI you can read back (self-hosted).
#
#   PYTHON=.venv/bin/python VERIFY=/path/to/fi_verify.py ./run_e2e.sh [happy|replay|retry|failure|negative|projects|privacy|matrix|all]
#
# Everything here is real: a Temporal dev server (`temporal server start-dev`), the Python
# `temporalio` SDK with OpenTelemetryPlugin, traceAI, and Future AGI. The model is whatever
# OPENAI_BASE_URL serves. A wire tap sits between the example and Future AGI and records what was
# sent (header names, never values; span payloads stay in $OUT, which must not be committed).
#
# Scenarios
#   happy     one workflow: trace hierarchy, model and token fields, one trace, spans sent exactly once
#   replay    forced replay three ways: a worker with no workflow cache (every workflow task replays
#             the whole history), a Replayer over the stored history, and a worker restart in the
#             middle of a workflow. The span count must not change.
#   retry     the tool activity fails once and Temporal retries it: both attempts are kept
#   failure   the model call fails on every attempt: ERROR spans, workflow fails
#   negative  plugin missing on the worker, plugin missing on the starter, starter that exits
#             without flushing (and with a flush)
#   projects  two projects do not read each other; a starter and a worker in different projects
#             split one trace
#   privacy   content off (FI_HIDE_* + error text removed): a unique marker must be absent from every
#             stored column and from the wire; then the opt-in (defaults + KEEP_TEMPORAL_ERROR_TEXT):
#             the marker must be present
#   matrix    happy + replay with PYTHON_ALT (for example Python 3.10) and/or TEMPORALIO_ALT_PYTHON
#
# Environment (defaults in brackets)
#   FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL   Future AGI keys and base URL (required)
#   OPENAI_API_KEY, OPENAI_BASE_URL          model endpoint (OPENAI_BASE_URL optional)
#   MODEL [gpt-6-luna]  PYTHON [python3]  PYTHON_ALT  TEMPORAL_CLI [temporal]
#   VERIFY      fi_verify.py of the local stack (required)   OUT [./evidence]
#   FI_PROJECT_PREFIX [th8103-rest-temporal]  RUN_ID [MMDD-HHMM; empty = no suffix]
#   FI_PG_CONTAINER, FI_CH_CONTAINER         the stack's containers (privacy scan)
#   ports: TEMPORAL_PORT [27253] TAP_PORT [27260]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-all}"
PY="${PYTHON:-python3}"
OUT="${OUT:-$PWD/evidence}"
PREFIX="${FI_PROJECT_PREFIX:-th8103-rest-temporal}"
RUN_ID="${RUN_ID-$(date +%m%d-%H%M)}"
BASE="$PREFIX${RUN_ID:+-$RUN_ID}"
: "${FI_API_KEY:?set FI_API_KEY}" "${FI_SECRET_KEY:?set FI_SECRET_KEY}" "${FI_BASE_URL:?set FI_BASE_URL}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}" "${VERIFY:?set VERIFY to fi_verify.py}"
export MODEL="${MODEL:-gpt-6-luna}"
TEMPORAL_CLI="${TEMPORAL_CLI:-temporal}"
TEMPORAL_PORT="${TEMPORAL_PORT:-27253}" TAP_PORT="${TAP_PORT:-27260}"
export TEMPORAL_ADDRESS="127.0.0.1:$TEMPORAL_PORT"
REAL_FI_BASE_URL="${FI_BASE_URL%/}"
mkdir -p "$OUT"
SUMMARY="$OUT/summary-$MODE.txt"
: >"$SUMMARY"
FAILED=0
TEMPORAL_PID="" TAP_PID="" WORKER_PID=""

say() { printf '\n== %s\n' "$*"; }
note() { printf '%s\n' "$*" | tee -a "$SUMMARY"; }
fail() { note "FAIL  $*"; FAILED=1; }
marker() { "$PY" -c 'import secrets; print("tmp" + secrets.token_hex(6))'; }
wid() { echo "$1-$(date +%H%M%S)-$RANDOM"; }

wait_port() { # port seconds
  local i=0
  until nc -z 127.0.0.1 "$1" 2>/dev/null; do i=$((i + 1)); [ "$i" -gt $(($2 * 4)) ] && return 1; sleep 0.25; done
}

start_temporal() {
  [ -n "$TEMPORAL_PID" ] && return 0
  if nc -z 127.0.0.1 "$TEMPORAL_PORT" 2>/dev/null; then fail "port $TEMPORAL_PORT is already in use: set TEMPORAL_PORT"; exit 1; fi
  "$TEMPORAL_CLI" server start-dev --headless --ip 127.0.0.1 --port "$TEMPORAL_PORT" --http-port $((TEMPORAL_PORT + 1)) \
    --metrics-port $((TEMPORAL_PORT + 2)) --log-level error >"$OUT/temporal-dev.log" 2>&1 &
  TEMPORAL_PID=$!
  wait_port "$TEMPORAL_PORT" 30 || { fail "temporal dev server did not start"; exit 1; }
  sleep 2
  "$TEMPORAL_CLI" --version | head -1 | tee -a "$SUMMARY"
}
stop_temporal() {
  if [ -n "$TEMPORAL_PID" ]; then kill "$TEMPORAL_PID" 2>/dev/null || true; wait "$TEMPORAL_PID" 2>/dev/null || true; fi
  TEMPORAL_PID=""
}

start_tap() { # name
  TAP_EXPECT_API_KEY="$FI_API_KEY" TAP_EXPECT_SECRET_KEY="$FI_SECRET_KEY" \
    "$PY" "$HERE/tools/wire_tap.py" --listen "$TAP_PORT" --out "$OUT/wire-$1.jsonl" --forward "$REAL_FI_BASE_URL" \
    >"$OUT/tap-$1.log" 2>&1 &
  TAP_PID=$!
  wait_port "$TAP_PORT" 10
  : >"$OUT/wire-$1.jsonl"
}
stop_tap() { [ -n "$TAP_PID" ] && kill "$TAP_PID" 2>/dev/null || true; TAP_PID=""; sleep 0.5; }

# Run python code of the example against the tap. $1 = project; the rest = environment assignments
# are passed through `env`.
fi_env() { env FI_BASE_URL="http://127.0.0.1:$TAP_PORT" FI_PROJECT_NAME="$1" "${@:2}"; }

start_worker() { # name project [env assignments...]
  local name="$1" project="$2"; shift 2
  # `env` is started directly (not through a function) so that $! is the worker's own pid
  env FI_BASE_URL="http://127.0.0.1:$TAP_PORT" FI_PROJECT_NAME="$project" "$@" "$PY" "$HERE/worker.py" >"$OUT/worker-$name.log" 2>&1 &
  WORKER_PID=$!
  local i=0
  until grep -q "worker ready" "$OUT/worker-$name.log" 2>/dev/null; do
    i=$((i + 1)); [ "$i" -gt 120 ] && { fail "worker $name did not start"; return 1; }; sleep 0.25
  done
}
stop_worker() { # SIGTERM: the worker flushes its spans and exits
  if [ -n "$WORKER_PID" ]; then
    kill -TERM "$WORKER_PID" 2>/dev/null || true
    local i=0
    while kill -0 "$WORKER_PID" 2>/dev/null; do i=$((i + 1)); [ "$i" -gt 120 ] && { kill -9 "$WORKER_PID"; fail "worker did not stop on SIGTERM"; break; }; sleep 0.25; done
    wait "$WORKER_PID" 2>/dev/null || true
  fi
  WORKER_PID=""
}

starter() { # name project [env assignments...] -- starter args
  local name="$1" project="$2"; shift 2
  local envs=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do envs+=("$1"); shift; done
  shift
  fi_env "$project" ${envs[@]+"${envs[@]}"} "$PY" "$HERE/starter.py" "$@" >"$OUT/starter-$name.log" 2>&1 || true
}

verify() { # project min-spans json-out [fi_verify args]
  local project="$1" min="$2" json="$3"; shift 3
  local n=0 out
  while [ "$n" -lt 8 ]; do
    out="$("$PY" "$VERIFY" --project "$project" --wait 90 --min-spans "$min" --json "$json" "$@" 2>&1)" || true
    if echo "$out" | grep -q "clickhouse error"; then n=$((n + 1)); note "  clickhouse busy, retry $n"; sleep 40; continue; fi
    echo "$out" >"${json%.json}.verify.txt"
    echo "$out" | grep -E "^(project|traces=)|PASS|FAIL" | tee -a "$SUMMARY"
    echo "$out" | grep -q "^PASS" && return 0
    return 1
  done
  fail "fi_verify kept hitting clickhouse errors for $project"
  return 1
}

check() { # label cmd...
  local label="$1"; shift
  if "$@" >"$OUT/check-$label.txt" 2>&1; then
    note "PASS  $label: $(grep -c '^PASS' "$OUT/check-$label.txt") rules"
  else
    fail "$label"; sed 's/^/    /' "$OUT/check-$label.txt" | tee -a "$SUMMARY"
  fi
}
check_fails() { # label cmd... : the command must fail (a deliberate misconfiguration)
  local label="$1"; shift
  if "$@" >"$OUT/check-$label.txt" 2>&1; then
    fail "$label: expected the check to fail, it passed"
  else
    note "PASS  $label (check fails as expected)"; grep '^FAIL' "$OUT/check-$label.txt" | sed 's/^/    /' | tee -a "$SUMMARY"
  fi
}

QUESTION="What is the weather in Lisbon today?"
WF="$PREFIX-wf"

# --------------------------------------------------------------------------------------------
scenario_happy() {
  say "happy: one workflow, project $BASE"
  start_tap happy; start_worker happy "$BASE"
  local id; id="$(wid happy)"
  starter happy "$BASE" -- "$QUESTION" --id "$id"
  stop_worker; stop_tap
  note "answer: $(head -c 120 "$OUT/starter-happy.log" | tr '\n' ' ')"
  verify "$BASE" 11 "$OUT/spans-happy.json" --expect-type llm --expect-type tool || fail "happy: fi_verify"
  check happy-trace "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-happy.json" --workflow "$id" --llm-spans 2 \
    --expect "StartWorkflow:WeatherAgentWorkflow=1" --expect "RunWorkflow:WeatherAgentWorkflow=1" \
    --expect "StartActivity:llm_plan=1" --expect "RunActivity:llm_plan=1" --expect "RunActivity:get_weather=1" \
    --expect "RunActivity:llm_answer=1" --expect "ChatCompletion=2" --expect "get_weather=1"
  check happy-wire "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-happy.jsonl" --project "$BASE" --expect "RunWorkflow:WeatherAgentWorkflow=1"
}

# --------------------------------------------------------------------------------------------
history_tasks() { # workflow id -> number of completed workflow tasks
  "$TEMPORAL_CLI" workflow show --address "$TEMPORAL_ADDRESS" -w "$1" --output json |
    "$PY" -c 'import json,sys; print(sum(1 for e in json.load(sys.stdin)["events"] if e["eventType"]=="EVENT_TYPE_WORKFLOW_TASK_COMPLETED"))'
}
wait_status() { # workflow id, status text
  local i=0
  until "$TEMPORAL_CLI" workflow describe --address "$TEMPORAL_ADDRESS" -w "$1" 2>/dev/null | grep -qE "Status +$2"; do
    i=$((i + 1)); [ "$i" -gt 240 ] && return 1; sleep 0.5
  done
}
wait_event() { # workflow id, event type, count
  local i=0 n
  while :; do
    n="$("$TEMPORAL_CLI" workflow show --address "$TEMPORAL_ADDRESS" -w "$1" --output json 2>/dev/null |
      "$PY" -c "import json,sys; print(sum(1 for e in json.load(sys.stdin)['events'] if e['eventType']=='$2'))" 2>/dev/null || echo 0)"
    [ "${n:-0}" -ge "$3" ] && return 0
    i=$((i + 1)); [ "$i" -gt 240 ] && return 1; sleep 0.5
  done
}

scenario_replay() {
  local project="$BASE-replay" id n
  say "replay: project $project"
  # (a) no workflow cache: every workflow task replays the whole history from the first event
  start_tap replay-a; start_worker replay-a "$project" MAX_CACHED_WORKFLOWS=0
  id="$(wid replay-nocache)"
  starter replay-a "$project" -- "$QUESTION" --id "$id"
  stop_worker; stop_tap
  n="$(history_tasks "$id")"
  note "replay (a) no cache: workflow $id ran $n workflow tasks, each one replayed the history from the start"
  verify "$project" 11 "$OUT/spans-replay-a.json" || fail "replay (a): fi_verify"
  check replay-a-trace "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-replay-a.json" --workflow "$id" --llm-spans 2 \
    --expect "RunWorkflow:WeatherAgentWorkflow=1" --expect "StartActivity:llm_plan=1" --expect "StartActivity:get_weather=1" --expect "StartActivity:llm_answer=1"
  check replay-a-wire "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-replay-a.jsonl" --project "$project" \
    --expect "RunWorkflow:WeatherAgentWorkflow=1" --expect "StartActivity:llm_plan=1" --expect "StartWorkflow:WeatherAgentWorkflow=1"

  # (b) Replayer over the stored history of (a), with tracing on: nothing may be exported
  start_tap replay-b
  fi_env "$project" "$PY" "$HERE/tools/replay_check.py" "$id" 2>&1 | tail -1 | tee -a "$SUMMARY"
  stop_tap
  check replay-b-wire "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-replay-b.jsonl" --allow-empty --total 0

  # (c) worker restart in the middle of a workflow: it waits for a signal after the first model call
  start_tap replay-c; start_worker replay-c1 "$project"
  id="$(wid replay-restart)"
  starter replay-c "$project" -- "$QUESTION" --id "$id" --approval
  wait_event "$id" EVENT_TYPE_ACTIVITY_TASK_COMPLETED 1 || fail "replay (c): first model call did not finish"
  stop_worker                                      # SIGTERM: flushes the spans of the first worker
  start_worker replay-c2 "$project"                # a cold worker: no cached workflow, it replays the history
  "$TEMPORAL_CLI" workflow signal --address "$TEMPORAL_ADDRESS" -w "$id" --name approve >/dev/null
  wait_status "$id" COMPLETED || fail "replay (c): workflow did not complete"
  stop_worker; stop_tap
  note "replay (c) restart: workflow $id finished on a second worker process"
  verify "$project" 23 "$OUT/spans-replay-c.json" || fail "replay (c): fi_verify"
  check replay-c-trace "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-replay-c.json" --workflow "$id" --llm-spans 2 \
    --ignore HandleSignal --expect "RunWorkflow:WeatherAgentWorkflow=1" --expect "StartActivity:llm_plan=1" --expect "RunActivity:llm_plan=1"
  check replay-c-wire "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-replay-c.jsonl" --project "$project" \
    --expect "RunWorkflow:WeatherAgentWorkflow=1" --expect "StartActivity:llm_plan=1" --expect "StartWorkflow:WeatherAgentWorkflow=1"
}

# --------------------------------------------------------------------------------------------
scenario_retry() {
  local project="$BASE-retry"
  say "retry: project $project"
  start_tap retry; start_worker retry "$project"
  local id; id="$(wid retry)"
  starter retry "$project" -- "$QUESTION" --id "$id" --flaky
  stop_worker; stop_tap
  verify "$project" 13 "$OUT/spans-retry.json" || fail "retry: fi_verify"
  check retry-trace "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-retry.json" --workflow "$id" --llm-spans 2 \
    --expect "StartActivity:get_weather=1" --expect "RunActivity:get_weather=2" --expect "get_weather=2" \
    --errors "RunActivity:get_weather=1" --errors "get_weather=1" --errors "RunWorkflow:WeatherAgentWorkflow=0"
  check retry-wire "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-retry.jsonl" --project "$project" \
    --expect "RunActivity:get_weather=2" --expect "StartActivity:get_weather=1"
}

scenario_failure() {
  local project="$BASE-failure"
  say "failure: project $project"
  start_tap failure; start_worker failure "$project"
  local id; id="$(wid failure)"
  starter failure "$project" -- "$QUESTION" --id "$id" --model "no-such-model-$RANDOM"
  stop_worker; stop_tap
  note "starter exit text: $(tail -c 160 "$OUT/starter-failure.log" | tr '\n' ' ')"
  verify "$project" 7 "$OUT/spans-failure.json" || fail "failure: fi_verify"
  check failure-trace "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-failure.json" --workflow "$id" --llm-spans 2 \
    --expect "RunActivity:llm_plan=2" --expect "ChatCompletion=2" --expect "RunWorkflow:WeatherAgentWorkflow=1" \
    --errors "RunActivity:llm_plan=2" --errors "ChatCompletion=2" --errors "RunWorkflow:WeatherAgentWorkflow=1" \
    --errors "StartWorkflow:WeatherAgentWorkflow=0"
}

# --------------------------------------------------------------------------------------------
scenario_negative() {
  local project="$BASE-negative" id
  say "negative: project $project"
  # worker without the plugin, starter with it: the model and tool spans lose their parent
  start_tap neg-1
  env FI_BASE_URL="http://127.0.0.1:$TAP_PORT" FI_PROJECT_NAME="$project" "$PY" "$HERE/tools/negative.py" worker-no-plugin \
    >"$OUT/worker-neg-1.log" 2>&1 &
  WORKER_PID=$!
  until grep -q "worker ready" "$OUT/worker-neg-1.log" 2>/dev/null; do sleep 0.25; done
  id="$(wid neg-worker)"
  fi_env "$project" "$PY" "$HERE/tools/negative.py" starter "$QUESTION" --id "$id" >"$OUT/starter-neg-1.log" 2>&1 || true
  stop_worker; stop_tap
  verify "$project" 4 "$OUT/spans-neg-1.json" || true
  check_fails neg-worker-without-plugin "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-neg-1.json" --llm-spans 2
  note "  traces seen: $("$PY" - "$OUT/spans-neg-1.json" <<'PY'
import json, sys
spans = json.load(open(sys.argv[1]))
traces = {}
for s in spans:
    traces.setdefault(s["trace_id"], []).append(s["name"])
print(json.dumps(sorted(traces.values())))
PY
)"

  # starter without the plugin, worker with it: the workflow starts its own trace
  project="$BASE-negative2"
  start_tap neg-2; start_worker neg-2 "$project"
  id="$(wid neg-starter)"
  fi_env "$project" "$PY" "$HERE/tools/negative.py" starter "$QUESTION" --id "$id" --no-plugin >"$OUT/starter-neg-2.log" 2>&1 || true
  stop_worker; stop_tap
  verify "$project" 10 "$OUT/spans-neg-2.json" || true
  check neg-starter-without-plugin "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-neg-2.json" --workflow "$id" --no-start-workflow \
    --expect "StartWorkflow:WeatherAgentWorkflow=0" --expect "RunWorkflow:WeatherAgentWorkflow=1"

  # a fire-and-forget starter that exits through os._exit(): the StartWorkflow span is lost unless it flushes first
  project="$BASE-negative3"
  # each leg has its own task queue, so the workflow it leaves running is not picked up by a later scenario
  start_tap neg-3a; start_worker neg-3a "$project" TASK_QUEUE=queue-neg-3a
  fi_env "$project" TASK_QUEUE=queue-neg-3a "$PY" "$HERE/tools/negative.py" starter "$QUESTION" --id "$(wid neg-exit)" --no-wait --os-exit >"$OUT/starter-neg-3a.log" 2>&1 || true
  stop_worker; stop_tap
  check neg-os-exit-no-flush "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-neg-3a.jsonl" --allow-empty --expect "StartWorkflow:WeatherAgentWorkflow=0"
  start_tap neg-3b; start_worker neg-3b "$project" TASK_QUEUE=queue-neg-3b
  fi_env "$project" TASK_QUEUE=queue-neg-3b "$PY" "$HERE/tools/negative.py" starter "$QUESTION" --id "$(wid neg-exit-flush)" --no-wait --os-exit --flush >"$OUT/starter-neg-3b.log" 2>&1 || true
  stop_worker; stop_tap
  check neg-os-exit-with-flush "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-neg-3b.jsonl" --expect "StartWorkflow:WeatherAgentWorkflow=1"
}

# --------------------------------------------------------------------------------------------
scenario_projects() {
  local pa="$BASE-proj-a" pb="$BASE-proj-b" ida idb ids
  say "projects: $pa and $pb"
  start_tap projects
  start_worker proj-a "$pa" TASK_QUEUE=queue-a; local wa="$WORKER_PID"
  start_worker proj-b "$pb" TASK_QUEUE=queue-b; local wb="$WORKER_PID"
  ida="$(wid proj-a)"; idb="$(wid proj-b)"; ids="$(wid proj-split)"
  starter proj-a "$pa" TASK_QUEUE=queue-a -- "$QUESTION" --id "$ida"
  starter proj-b "$pb" TASK_QUEUE=queue-b -- "$QUESTION" --id "$idb"
  # a starter in project B whose workflow runs on the worker of project A
  starter proj-split "$pb" TASK_QUEUE=queue-a -- "$QUESTION" --id "$ids"
  WORKER_PID="$wa"; stop_worker; WORKER_PID="$wb"; stop_worker; stop_tap
  verify "$pa" 21 "$OUT/spans-proj-a.json" || fail "projects: fi_verify a"
  verify "$pb" 12 "$OUT/spans-proj-b.json" || fail "projects: fi_verify b"
  check proj-a-only-a "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-proj-a.json" --workflow "$ida" --llm-spans 2
  check proj-b-only-b "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-proj-b.json" --workflow "$idb" --llm-spans 2
  "$PY" - "$OUT/spans-proj-a.json" "$OUT/spans-proj-b.json" "$ida" "$idb" "$ids" <<'PY' | tee -a "$SUMMARY"
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
ida, idb, ids = sys.argv[3:6]
def sessions(spans):
    return {(s.get("attrs_string") or {}).get("session.id") for s in spans}
def names(spans, wf):
    return sorted(s["name"] for s in spans if (s.get("attrs_string") or {}).get("session.id") == wf)
ok = ida in sessions(a) and idb not in sessions(a) and idb in sessions(b) and ida not in sessions(b)
print(("PASS" if ok else "FAIL") + "  no cross-project read: A holds workflow A only, B holds workflow B only")
split_a, split_b = names(a, ids), names(b, ids)
print(f"split workflow (starter in B, worker in A): project A holds {len(split_a)} spans, project B holds {split_b}")
ok2 = "StartWorkflow:WeatherAgentWorkflow" in split_b and "StartWorkflow:WeatherAgentWorkflow" not in split_a and "RunWorkflow:WeatherAgentWorkflow" in split_a
print(("PASS" if ok2 else "FAIL") + "  a starter and a worker in different projects split the trace across the two projects")
sys.exit(0 if ok and ok2 else 1)
PY
  [ "${PIPESTATUS[0]}" -eq 0 ] || fail "projects: cross-project checks"
}

# --------------------------------------------------------------------------------------------
HIDE_ENV=(FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true FI_HIDE_INPUT_MESSAGES=true FI_HIDE_OUTPUT_MESSAGES=true FI_HIDE_LLM_INVOCATION_PARAMETERS=true)
# Things that must never be stored, in either mode: the user, the host, local paths, stack traces, keys,
# the model endpoint and the Temporal address.
NEVER=("user=$(id -un)" "host=$(hostname)" "home=$HOME" "cwd=$HERE" "Traceback" "exception.stacktrace"
  "model_url=${OPENAI_BASE_URL:-http://openai.invalid}" "temporal=$TEMPORAL_ADDRESS"
  "api_key=$FI_API_KEY" "secret_key=$FI_SECRET_KEY" "model_key=$OPENAI_API_KEY")
needle_args() { # needle...  -> --needle args on stdout, one per line
  for n in "$@"; do printf -- '--needle\n%s\n' "$n"; done
}

privacy_leg() { # label project marker error-marker [env assignments...]
  local label="$1" project="$2" m="$3" e="$4"; shift 4
  start_tap "priv-$label"; start_worker "priv-$label" "$project" "$@"
  # the marker is in the question (prompt) and in the city the tool receives (tool arguments, result, error text)
  starter "priv-$label-1" "$project" "$@" -- "What is the weather in ${m}city today?" --id "$(wid priv-$label)" --flaky
  # the error marker is only in the model name, so only in the provider's error text
  starter "priv-$label-2" "$project" "$@" -- "What is the weather in Lisbon today?" --id "$(wid priv-$label-err)" --model "$e"
  stop_worker; stop_tap
  verify "$project" 20 "$OUT/spans-priv-$label.json" || fail "privacy $label: fi_verify"
}

scenario_privacy() {
  local m e off on
  m="$(marker)"; e="$(marker)"
  off="$BASE-priv-off"; on="$BASE-priv-on"
  say "privacy: markers $m (content), $e (error text only)"
  # content off: the five FI_HIDE_* switches on both processes, error text removed (the default)
  privacy_leg off "$off" "$m" "$e" "${HIDE_ENV[@]}"
  local args=()
  while IFS= read -r line; do args+=("$line"); done < <(needle_args "$m" "$e" "${NEVER[@]}")
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$off" --ignore-case "${args[@]}" \
      --wire "$OUT/wire-priv-off.jsonl" --json "$OUT/scan-priv-off.json" >"$OUT/scan-priv-off.txt" 2>&1; then
    note "PASS  privacy content-off: marker, error marker, user, host, home, paths, endpoints, keys, stack traces: 0 occurrences"
  else
    fail "privacy content-off"; sed 's/^/    /' "$OUT/scan-priv-off.txt" | tee -a "$SUMMARY"
  fi
  head -1 "$OUT/scan-priv-off.txt" | tee -a "$SUMMARY"
  # the documented opt-in: traceAI defaults (content on) + KEEP_TEMPORAL_ERROR_TEXT=true
  privacy_leg on "$on" "$m" "$e" KEEP_TEMPORAL_ERROR_TEXT=true
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$on" --needle "$m" --needle "$e" --expect-found \
      --json "$OUT/scan-priv-on.json" >"$OUT/scan-priv-on.txt" 2>&1; then
    note "PASS  privacy opt-in: marker and error marker are stored when content capture and error text are on"
  else
    fail "privacy opt-in"; sed 's/^/    /' "$OUT/scan-priv-on.txt" | tee -a "$SUMMARY"
  fi
  "$PY" "$HERE/tools/marker_locations.py" "$OUT/spans-priv-on.json" "content=$m" "error_text=$e" | tee -a "$SUMMARY"
  # stack traces, local paths, host names and keys stay out even with the opt-in
  args=()
  while IFS= read -r line; do args+=("$line"); done < <(needle_args "${NEVER[@]}")
  if "$PY" "$HERE/tools/scan_local_stack.py" --project "$on" "${args[@]}" --wire "$OUT/wire-priv-on.jsonl" >"$OUT/scan-priv-on-never.txt" 2>&1; then
    note "PASS  privacy opt-in still removes stack traces, user, host, home, paths, endpoints and keys"
  else
    fail "privacy opt-in never-list"; sed 's/^/    /' "$OUT/scan-priv-on-never.txt" | tee -a "$SUMMARY"
  fi
}

# --------------------------------------------------------------------------------------------
scenario_matrix() {
  say "matrix: PYTHON_ALT=${PYTHON_ALT:-unset}"
  if [ -z "${PYTHON_ALT:-}" ]; then note "SKIP  matrix: set PYTHON_ALT"; return 0; fi
  local project="$BASE-matrix" id
  local saved="$PY"; PY="$PYTHON_ALT"
  "$PY" -c 'import sys, temporalio; from importlib.metadata import version; print("matrix python", sys.version.split()[0], "temporalio", version("temporalio"))' | tee -a "$SUMMARY"
  start_tap matrix; start_worker matrix "$project" MAX_CACHED_WORKFLOWS=0
  id="$(wid matrix)"
  starter matrix "$project" -- "$QUESTION" --id "$id"
  stop_worker; stop_tap
  PY="$saved"
  verify "$project" 11 "$OUT/spans-matrix.json" || fail "matrix: fi_verify"
  check matrix-trace "$PY" "$HERE/tools/check_trace.py" "$OUT/spans-matrix.json" --workflow "$id" --llm-spans 2 --expect "RunWorkflow:WeatherAgentWorkflow=1"
  check matrix-wire "$PY" "$HERE/tools/wire_check.py" "$OUT/wire-matrix.jsonl" --project "$project" --expect "RunWorkflow:WeatherAgentWorkflow=1"
}

cleanup() { stop_worker; stop_tap; stop_temporal; }
trap cleanup EXIT

start_temporal
case "$MODE" in
  happy) scenario_happy ;;
  replay) scenario_replay ;;
  retry) scenario_retry ;;
  failure) scenario_failure ;;
  negative) scenario_negative ;;
  projects) scenario_projects ;;
  privacy) scenario_privacy ;;
  matrix) scenario_matrix ;;
  all) scenario_happy; scenario_replay; scenario_retry; scenario_failure; scenario_negative; scenario_projects; scenario_privacy; scenario_matrix ;;
  *) echo "unknown scenario: $MODE" >&2; exit 2 ;;
esac
say "done: $([ "$FAILED" -eq 0 ] && echo PASS || echo FAIL)"
note "RESULT: $([ "$FAILED" -eq 0 ] && echo PASS || echo FAIL)"
exit "$FAILED"
