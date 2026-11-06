#!/usr/bin/env bash
# Build the PINNED ClickHouse/ai-sdk-cpp, run its ai::langfuse module against a loopback capture stub, and
# check what it puts on the wire. Nothing is sent to Future AGI or to any Langfuse server.
#
# needs : git, cmake >= 3.16, a C++20 compiler, OpenSSL (set OPENSSL_ROOT_DIR if cmake cannot find it),
#         python3, network access to GitHub (the build downloads zlib), and an OpenAI-compatible endpoint
#         for the model call.
# env   : PROBE_API_KEY (key for the endpoint), PROBE_OPENAI_BASE (default http://127.0.0.1:8317, no /v1),
#         PROBE_MODEL (default gpt-6-luna), WORK_DIR (default: a fresh temp dir), STUB_PORT (default 18251)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="${CHECK_PIN_SHA:-9d8cd18200a33b64460c9101ed0dd6d4988bea61}"
WORK="${WORK_DIR:-$(mktemp -d)}"
PORT="${STUB_PORT:-18251}"
OUT="$WORK/out"; mkdir -p "$OUT" "$WORK/src"

if [ ! -d "$WORK/src/ai-sdk-cpp/.git" ]; then
  mkdir -p "$WORK/src/ai-sdk-cpp"
  git -C "$WORK/src/ai-sdk-cpp" init -q
  git -C "$WORK/src/ai-sdk-cpp" remote add origin https://github.com/ClickHouse/ai-sdk-cpp.git
  git -C "$WORK/src/ai-sdk-cpp" fetch -q --depth 1 origin "$PIN"
  git -C "$WORK/src/ai-sdk-cpp" checkout -q FETCH_HEAD
fi
test "$(git -C "$WORK/src/ai-sdk-cpp" rev-parse HEAD)" = "$PIN" || { echo "wrong commit"; exit 2; }

cmake -S "$HERE" -B "$WORK/build" -DAI_SDK_SRC="$WORK/src/ai-sdk-cpp" -DCMAKE_BUILD_TYPE=Release -Wno-dev >/dev/null
cmake --build "$WORK/build" -j4 --target probe >/dev/null

export PROBE_LF_HOST="http://127.0.0.1:$PORT"
for mode in run fail noend strict-down best-down; do
  rm -f "$OUT/$mode.jsonl"
  python3 -I "$HERE/capture_stub.py" "$OUT/$mode.jsonl" "$PORT" & stub=$!
  sleep 0.7
  PROBE_MARKER="MARKER-$mode" "$WORK/build/probe" "$mode" > "$OUT/$mode.stdout.txt" 2>&1 || true
  kill "$stub" 2>/dev/null || true; wait "$stub" 2>/dev/null || true
done
echo "output in $OUT"
python3 -I "$HERE/check_wire.py" "$OUT"
