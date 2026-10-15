#!/usr/bin/env bash
# Offline tests: recorded goose 1.54.0 span fixtures, no network. The collector
# test runs otel-collector.yaml in otelcol-contrib (skipped if it is not found).
# `pip install opentelemetry-proto` also runs the recorder unit test.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 "$ROOT/test_contract.py"
python3 "$ROOT/test_collector.py"
