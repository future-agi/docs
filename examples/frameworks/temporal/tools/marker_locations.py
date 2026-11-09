#!/usr/bin/env python3
"""Say where in the stored spans a marker occurs: span name and field, never the content.

    marker_locations.py spans.json NEEDLE [NEEDLE ...]

Input is the span list that fi_verify.py --json writes. Fields searched: status_message, input_head,
output_head and every key of attrs_string. A needle written LABEL=VALUE is reported by its label.
"""
import json
import re
import sys
from collections import defaultdict


def locations(spans: list[dict], needle: str) -> dict[str, list[str]]:
    found = defaultdict(set)
    for s in spans:
        for field in ("status_message", "input_head", "output_head"):
            if needle in str(s.get(field) or ""):
                found[s["name"]].add(field)
        for key, value in (s.get("attrs_string") or {}).items():
            if needle in str(value):
                found[s["name"]].add(key)
    return {name: sorted(fields) for name, fields in sorted(found.items())}


def main() -> int:
    spans = json.load(open(sys.argv[1]))
    for raw in sys.argv[2:]:
        m = re.match(r"^([a-z0-9_]+)=(.+)$", raw)
        label, needle = (m.group(1), m.group(2)) if m else (raw[:8] + "...", raw)
        print(f"{label}: {json.dumps(locations(spans, needle))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
