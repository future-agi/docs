#!/usr/bin/env bash
# Offline contract test: recorded goose 1.54.0 span fixtures, no network.
# `pip install opentelemetry-proto` also runs the recorder unit test.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 "$ROOT/test_contract.py"
