#!/usr/bin/env python3
"""Check what the AI SDK C++ Langfuse module put on the wire, from the probe's output directory.

usage: check_wire.py <out-dir>

<out-dir> holds, per mode (run, fail, noend, strict-down, best-down):
  <mode>.stdout.txt   the probe's stdout
  <mode>.jsonl        the capture stub's records (absent when no request arrived)
Prints one PASS/FAIL line per expectation and exits 1 if any fails. Expectations are the facts stated on the
docs page; if upstream changes behaviour this fails and the page needs a new look.
"""
import json
import os
import re
import sys


def load(out, mode):
    path = os.path.join(out, mode + ".jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def stdout(out, mode):
    with open(os.path.join(out, mode + ".stdout.txt")) as f:
        return f.read()


def end_returns(text):
    m = re.search(r"end#1=(\d) end#2=(\d)", text)
    return (m.group(1), m.group(2)) if m else None


def check(out):
    results = []

    def ok(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # run: one tool call, one model call chain, end() twice
    reqs = load(out, "run")
    ok("run: exactly one POST although end() was called twice", len(reqs) == 1, f"{len(reqs)} requests")
    if reqs:
        r = reqs[0]
        batch = r["body"].get("batch", [])
        types = [e.get("type") for e in batch]
        ok("run: path is /api/public/ingestion", r["path"] == "/api/public/ingestion", r["path"])
        ok("run: body is JSON with a single 'batch' key (not OTLP)", list(r["body"].keys()) == ["batch"], str(list(r["body"].keys())))
        ok("run: Langfuse event types", types == ["trace-create", "span-create", "span-update", "generation-create"], str(types))
        ok("run: Authorization header is HTTP Basic", r["basic_auth_user"] != "", r["basic_auth_user"])
        names = {k.lower() for k in r["headers"]}
        ok("run: no X-Api-Key / X-Secret-Key header", not ({"x-api-key", "x-secret-key"} & names), str(sorted(names)))
        ok("run: Langfuse SDK marker headers", r["headers"].get("X-Langfuse-Sdk-Name") == "ai-sdk-cpp")
        ok("run: no OTLP resourceSpans anywhere in the body", "resourceSpans" not in json.dumps(r["body"]))
        gen = next((e["body"] for e in batch if e.get("type") == "generation-create"), {})
        span = next((e["body"] for e in batch if e.get("type") == "span-create"), {})
        usage = gen.get("usage", {})
        ok("run: generation carries model and token usage", bool(gen.get("model")) and usage.get("total", 0) > 0, str(usage))
        ok("run: tool span is a child of the generation", span.get("parentObservationId") == gen.get("id"))
    ret = end_returns(stdout(out, "run"))
    ok("run: both end() calls return true", ret == ("1", "1"), str(ret))

    # fail: API error still produces a batch with an ERROR generation
    reqs = load(out, "fail")
    ok("fail: one POST", len(reqs) == 1, f"{len(reqs)} requests")
    if reqs:
        gen = next((e["body"] for e in reqs[0]["body"].get("batch", []) if e.get("type") == "generation-create"), {})
        ok("fail: generation level is ERROR", gen.get("level") == "ERROR", str(gen.get("level")))
        ok("fail: statusMessage carries the provider's raw error text", bool(gen.get("statusMessage")))

    # noend: nothing is sent when the process exits without end()
    ok("noend: no POST at all", len(load(out, "noend")) == 0)
    ok("noend: probe reached the exit without end()", "exiting without end()" in stdout(out, "noend"))

    # unreachable host
    s = stdout(out, "strict-down")
    ok("strict-down: first end() false, second end() true (no retry)", end_returns(s) == ("0", "1"), str(end_returns(s)))
    b = stdout(out, "best-down")
    ok("best-down: both end() true", end_returns(b) == ("1", "1"), str(end_returns(b)))
    ok("no mode threw out of end()", not any("end() threw" in stdout(out, m) for m in ("run", "fail", "strict-down", "best-down")))
    return results


def main():
    results = check(sys.argv[1])
    for name, passed, detail in results:
        print(("PASS " if passed else "FAIL ") + name + (f"  [{detail}]" if detail and not passed else ""))
    failed = [r for r in results if not r[1]]
    print(f"{len(results) - len(failed)}/{len(results)} expectations hold")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
