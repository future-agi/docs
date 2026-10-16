#!/usr/bin/env python3
"""Turn a capture directory written by otlp_sink.py into one committed test fixture.

Writes ``<out>/<name>.json`` (all exported batches as one OTLP/JSON document, ids as hex, keys sorted)
and ``<out>/<name>.meta.json`` (how it was captured and the request log). Home-directory paths are
replaced so a fixture never holds a username.

Usage: python3 make_fixture.py CAPTURE_DIR NAME --out tests/fixtures --mode v2 --content off \
         --marker MARK_x --version 1.105.1 --runner docker [--scrubbed] [--scenarios-file scenarios.jsonl] [--note TEXT]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from otlp_contract import load_documents, norm_id, request_log

HOME = re.compile(r"/(Users|home)/[^/\"\\\s]+")


def hexify(node):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in ("traceId", "spanId", "parentSpanId") and isinstance(value, str):
                out[key] = norm_id(value)
            else:
                out[key] = hexify(value)
        return out
    if isinstance(node, list):
        return [hexify(x) for x in node]
    return node


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("capture")
    parser.add_argument("name")
    parser.add_argument("--out", default="tests/fixtures")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--marker", default="")
    parser.add_argument("--version", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument("--scrubbed", action="store_true")
    parser.add_argument("--scenarios-file", default="", help="scenarios.jsonl written by run_e2e.sh (send_requests.py output)")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    docs = load_documents(args.capture)
    merged = {"resourceSpans": [rs for doc in docs for rs in doc.get("resourceSpans", [])]}
    text = HOME.sub("/home/user", json.dumps(hexify(merged), indent=1, sort_keys=True))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.name}.json").write_text(text + "\n")
    scenarios = []
    if args.scenarios_file:
        scenarios = [
            {k: v for k, v in json.loads(line).items() if k != "call_id"}
            for line in Path(args.scenarios_file).read_text().splitlines()
            if line.strip()
        ]
    log = request_log(str(Path(args.capture) / "requests.jsonl"))
    meta = {
        "litellm_version": args.version,
        "runner": args.runner,
        "mode": args.mode,
        "content": args.content,
        "marker": args.marker,
        "scrubbed": args.scrubbed,
        "scenarios": scenarios,
        "note": args.note,
        "requests": [{k: r[k] for k in ("path", "signal", "content_type", "content_encoding", "auth_headers_present")} for r in log],
    }
    (out / f"{args.name}.meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out / (args.name + '.json')} ({len(merged['resourceSpans'])} ResourceSpans)")


if __name__ == "__main__":
    main()
