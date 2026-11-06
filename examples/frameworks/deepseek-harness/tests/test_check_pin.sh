#!/usr/bin/env bash
# Offline test of check_pin.sh using tiny local git repos. exit 0 = all pass.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"; T="$(mktemp -d)"; fail=0
mk() {  # $1 dir, $2 = "clean" | "dirty" | "nocontrol"
  mkdir -p "$1/packages/x" && git -C "$1" init -q
  case "$2" in
    nocontrol) echo "nothing" > "$1/packages/x/a.ts" ;;
    *) printf 'import sdk-logs; JsonLogsSerializer; dsh-otel-collector.deepseeksvc.com/v1/logs\n' > "$1/packages/x/a.ts" ;;
  esac
  [ "$2" = dirty ] && echo 'new OTLPTraceExporter()' > "$1/packages/x/b.ts"
  git -C "$1" add -A && git -C "$1" -c user.email=t@t -c user.name=t commit -q -m t
}
expect() {  # $1 name, $2 want, $3 got
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (want $2 got $3)"; fail=1; fi
}
mk "$T/clean" clean; mk "$T/dirty" dirty; mk "$T/nocontrol" nocontrol
bash "$HERE/check_pin.sh" "$T/clean" >/dev/null; expect "clean tree exits 0" 0 $?
bash "$HERE/check_pin.sh" "$T/dirty" >/dev/null; expect "trace exporter present exits 1" 1 $?
bash "$HERE/check_pin.sh" "$T/nocontrol" >/dev/null; expect "missing positive control exits 2" 2 $?
bash "$HERE/check_pin.sh" "$T/not-a-repo" >/dev/null 2>&1; expect "non-repo exits 2" 2 $?
rm -rf "$T"; exit $fail
