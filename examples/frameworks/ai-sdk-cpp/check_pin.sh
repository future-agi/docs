#!/usr/bin/env bash
# TH-8251: does ClickHouse/ai-sdk-cpp contain any OTLP / OpenTelemetry export at the pinned commit?
#
# usage: check_pin.sh            shallow-clone the pinned commit into a fresh temp dir and search it
#        check_pin.sh <git-dir>  search an existing git checkout (the tests use this with tiny trees)
#
# exit 0  none of the OTLP terms is present: the claim on the docs page holds
# exit 1  at least one term is present: reopen TH-8251, the page is out of date
# exit 2  the search could not be trusted (clone failed, wrong commit, or a positive control found nothing)
#
# Positive controls are terms that MUST be present (the Langfuse client and the Anthropic header). A search
# that cannot find them proves nothing when it finds zero OTLP files.
set -u
PIN="${CHECK_PIN_SHA:-9d8cd18200a33b64460c9101ed0dd6d4988bea61}"
REPO="${CHECK_PIN_REPO:-https://github.com/ClickHouse/ai-sdk-cpp.git}"
read -r -a TERMS <<< "${CHECK_PIN_TERMS:-otlp opentelemetry exporter traceparent gen_ai /v1/traces}"
read -r -a CONTROLS <<< "${CHECK_PIN_CONTROLS:-langfuse x-api-key}"

dir="${1:-}"
if [ -z "$dir" ]; then
  dir="$(mktemp -d)/ai-sdk-cpp"
  mkdir -p "$dir" && git -C "$dir" init -q \
    && git -C "$dir" remote add origin "$REPO" \
    && git -C "$dir" fetch -q --depth 1 origin "$PIN" \
    && git -C "$dir" checkout -q FETCH_HEAD || { echo "clone of $REPO at $PIN failed"; exit 2; }
  upstream_main="$(git ls-remote "$REPO" refs/heads/main 2>/dev/null | cut -f1)"
  echo "upstream main : ${upstream_main:-unknown}$([ "$upstream_main" = "$PIN" ] && echo '  (same as the pin)')"
fi

head="$(git -C "$dir" rev-parse HEAD 2>/dev/null)" || { echo "$dir is not a git checkout"; exit 2; }
[ -z "${1:-}" ] && [ "$head" != "$PIN" ] && { echo "checked out $head, expected $PIN"; exit 2; }
echo "commit        : $head"
echo "tracked files : $(git -C "$dir" ls-files | wc -l | tr -d ' ')"
echo
count() { git -C "$dir" grep -i -l -F -e "$1" | wc -l | tr -d ' '; }

found=0
echo "OTLP terms (case-insensitive, all tracked files; 0 is the expected result)"
for t in "${TERMS[@]}"; do
  n="$(count "$t")"; printf '  %-14s %s files\n' "$t" "$n"
  [ "$n" != "0" ] && found=1
done
echo "positive controls (must be above 0 or the search is not trusted)"
bad=0
for t in "${CONTROLS[@]}"; do
  n="$(count "$t")"; printf '  %-14s %s files\n' "$t" "$n"
  [ "$n" = "0" ] && bad=1
done
if [ -f "$dir/src/langfuse/tracer.cpp" ]; then
  echo
  echo "Langfuse transport:"
  grep -n -E 'kIngestionPath = |"Authorization"|X-Langfuse-Sdk' "$dir/src/langfuse/tracer.cpp" | sed 's/^/  /'
fi
echo
[ "$bad" = "1" ] && { echo "RESULT: search not trusted (a positive control found nothing)"; exit 2; }
[ "$found" = "1" ] && { echo "RESULT: OTLP term present, reopen TH-8251"; exit 1; }
echo "RESULT: no OTLP or OpenTelemetry export in this tree"
exit 0
