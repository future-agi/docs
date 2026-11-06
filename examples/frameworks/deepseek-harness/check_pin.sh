#!/usr/bin/env bash
# TH-8265: does deepseek-ai/deepseek-harness (dsh) export OpenTelemetry TRACES?
#
# usage: check_pin.sh            shallow-fetch each pinned commit into a fresh temp dir and search it
#        check_pin.sh <git-dir>  search an existing git checkout (the tests use this with tiny trees)
#
# exit 0  no trace SDK or trace exporter in the source, and the OTLP logs exporter is still there:
#         the claims on the docs page hold
# exit 1  a trace term is present in source: reopen TH-8265, the page is out of date
# exit 2  the search could not be trusted (fetch failed, wrong commit, or a positive control found nothing)
#
# Trace terms are searched in packages/ and apps/ only, so lockfiles and the dependency catalog (which list
# transitive packages that no dsh source imports) cannot trigger a false alarm. The positive controls are the
# logs SDK and DeepSeek's own collector URL: a search that cannot find them proves nothing when it finds zero
# trace terms.
set -u
REPO="${CHECK_PIN_REPO:-https://github.com/deepseek-ai/deepseek-harness.git}"
# 86a40220 = tag dsh-v0.2.1-alpha.4 (head of master on 2026-10-16), 639ed015 = tag dsh-v0.2.0-rc.2 (npm "latest"),
# 5badb150 = the commit the original specification read (2026-10-03).
SHAS="${CHECK_PIN_SHAS:-86a402200d95fecef4529d969836f1fe13c6cb0d 639ed015397290b3745d163aafe02ffee4aa3f84 5badb15009ae1756c3afe0ae0cef1faafc290ccc}"
read -r -a TRACE_TERMS <<< "${CHECK_PIN_TRACE_TERMS:-sdk-trace exporter-trace OTLPTraceExporter TracerProvider getTracer startSpan /v1/traces traceparent gen_ai}"
read -r -a CONTROLS <<< "${CHECK_PIN_CONTROLS:-sdk-logs JsonLogsSerializer dsh-otel-collector.deepseeksvc.com/v1/logs}"

check_one() {  # $1 = git checkout dir
  local dir="$1" found=0 bad=0 n t
  echo "commit        : $(git -C "$dir" rev-parse HEAD 2>/dev/null)"
  echo "tracked files : $(git -C "$dir" ls-files | wc -l | tr -d ' ')"
  count() { git -C "$dir" grep -i -l -F -e "$1" -- packages apps 2>/dev/null | wc -l | tr -d ' '; }
  echo "trace terms in packages/ and apps/ (case-insensitive; 0 is the expected result)"
  for t in "${TRACE_TERMS[@]}"; do
    n="$(count "$t")"; printf '  %-46s %s files\n' "$t" "$n"
    [ "$n" != "0" ] && found=1
  done
  echo "positive controls (must be above 0 or the search is not trusted)"
  for t in "${CONTROLS[@]}"; do
    n="$(count "$t")"; printf '  %-46s %s files\n' "$t" "$n"
    [ "$n" = "0" ] && bad=1
  done
  [ "$bad" = "1" ] && return 2
  [ "$found" = "1" ] && return 1
  return 0
}

if [ -n "${1:-}" ]; then
  git -C "$1" rev-parse HEAD >/dev/null 2>&1 || { echo "$1 is not a git checkout"; exit 2; }
  check_one "$1"; rc=$?
else
  rc=0; tmp="$(mktemp -d)"
  for sha in $SHAS; do
    dir="$tmp/$sha"; mkdir -p "$dir"
    git -C "$dir" init -q && git -C "$dir" remote add origin "$REPO" \
      && git -C "$dir" fetch -q --depth 1 origin "$sha" && git -C "$dir" checkout -q FETCH_HEAD \
      || { echo "fetch of $REPO at $sha failed"; rc=2; continue; }
    [ "$(git -C "$dir" rev-parse HEAD)" = "$sha" ] || { echo "checked out a different commit than $sha"; rc=2; continue; }
    check_one "$dir"; r=$?; echo
    # worst result wins: 2 (untrusted) beats 1 (reopen) beats 0
    if [ "$r" = "2" ] || { [ "$r" = "1" ] && [ "$rc" != "2" ]; }; then rc="$r"; fi
  done
  echo "upstream master: $(git ls-remote "$REPO" refs/heads/master 2>/dev/null | cut -f1)"
  rm -rf "$tmp"
fi
echo
case "$rc" in
  0) echo "RESULT: no trace SDK or trace exporter in dsh source; the OTLP logs exporter is present" ;;
  1) echo "RESULT: a trace term is present, reopen TH-8265" ;;
  *) echo "RESULT: search not trusted (fetch failed, or a positive control found nothing)" ;;
esac
exit "$rc"
