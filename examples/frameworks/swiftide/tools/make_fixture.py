#!/usr/bin/env python3
"""Turn a content-off wire_tap.py capture into the replay fixture.

  make_fixture.py wire.jsonl tests/fixtures/swiftide-0.33.0-content-off.json

Merges the resourceSpans of every captured request into one OTLP/JSON ExportTraceServiceRequest
and renames the project to "swiftide-fixture". Refuses captures that contain span events or
attributes outside the content-off allow list (so a content-on capture cannot become a fixture).
"""
import json
import sys

ALLOWED = {"busy_ns", "idle_ns", "step_count", "target"}


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    resource_spans = []
    for line in open(src):
        rec = json.loads(line)
        for rs in rec.get("body", {}).get("resourceSpans", []):
            for kv in rs["resource"]["attributes"]:
                if kv["key"] == "project_name":
                    kv["value"] = {"stringValue": "swiftide-fixture"}
            for ss in rs.get("scopeSpans", []):
                for span in ss.get("spans", []):
                    if span.get("events"):
                        raise SystemExit(f"span {span['name']} has events: not a content-off capture")
                    extra = {a["key"] for a in span.get("attributes", [])} - ALLOWED
                    if extra:
                        raise SystemExit(f"span {span['name']} has attributes {sorted(extra)}")
            resource_spans.append(rs)
    with open(dst, "w") as f:
        json.dump({"resourceSpans": resource_spans}, f, indent=1)
        f.write("\n")
    print(f"wrote {dst}: {sum(len(ss['spans']) for rs in resource_spans for ss in rs['scopeSpans'])} spans")
    return 0


if __name__ == "__main__":
    sys.exit(main())
