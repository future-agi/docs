"""Record one agent run as an OTLP/JSON fixture (what the exporter sent, nothing more).

The run goes to a loopback recorder instead of Future AGI. Ids are written as lower-case
hex (OTLP/JSON), the resource ``project_name`` is replaced, and the model endpoint URL is
replaced by ``http://localhost:8000/v1``.

usage: MODEL_BASE_URL=... MODEL_API_KEY=... MODEL_ID=... \
       python scripts/record_fixture.py --variant traceai|openinference --out FILE [--hide]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path.insert(0, str(EXAMPLE / "tests"))

from otlp_recorder import Recorder  # noqa: E402

SCRIPTS = {"traceai": EXAMPLE / "app.py", "openinference": HERE / "openinference_variant.py"}
ID_KEYS = ("traceId", "spanId", "parentSpanId")


def to_hex(node):
    if isinstance(node, dict):
        return {k: (base64.b64decode(v).hex() if k in ID_KEYS and v else to_hex(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [to_hex(v) for v in node]
    return node


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=sorted(SCRIPTS), required=True)
    parser.add_argument("--scenario", default="chat")
    parser.add_argument("--out", required=True)
    parser.add_argument("--hide", action="store_true", help="FI_HIDE_INPUTS/OUTPUTS=true")
    args = parser.parse_args()

    with Recorder() as recorder:
        env = dict(os.environ, FI_BASE_URL=recorder.origin, FI_API_KEY="fixture-api-key",
                   FI_SECRET_KEY="fixture-secret-key", FI_PROJECT_NAME="open-agent-spec-fixture")
        if args.hide:
            env.update(FI_HIDE_INPUTS="true", FI_HIDE_OUTPUTS="true")
        proc = subprocess.run([sys.executable, str(SCRIPTS[args.variant]), args.scenario],
                              cwd=str(EXAMPLE), env=env, capture_output=True, text=True, timeout=300)
        print(proc.stdout.strip())
        resource_spans = [rs for r in recorder.requests for rs in r["otlp"].get("resourceSpans", [])]

    text = json.dumps({"resourceSpans": to_hex(resource_spans)}, indent=1, sort_keys=True)
    model_url = os.environ.get("MODEL_BASE_URL", "")
    if model_url:
        text = text.replace(model_url.rstrip("/"), "http://localhost:8000/v1")
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    spans = sum(len(ss.get("spans", [])) for rs in resource_spans for ss in rs.get("scopeSpans", []))
    print(f"wrote {args.out}: {spans} spans")
    return 0 if spans else 1


if __name__ == "__main__":
    sys.exit(main())
