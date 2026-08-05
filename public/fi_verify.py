"""fi_verify - checks a Future AGI integration against what the collector really received.

    python fi_verify.py preflight    closes G1, before any code is touched
    python fi_verify.py check        all ten gates, after one real request

Python 3.10+. No dependency beyond the OpenTelemetry SDK.
"""
import json, os, sys, time, urllib.error, urllib.request

EP = os.getenv("FI_ENDPOINT", "https://api.futureagi.com/tracer/v1/traces")
SPANS = os.getenv("FI_VERIFY_FILE", ".fi_verify/spans.jsonl")
DIR = os.path.dirname(SPANS) or "."

# Two spellings are read for each: the Future AGI SDK writes the first, a plain
# OpenTelemetry setup writes the second.
KIND = ("gen_ai.span.kind", "fi.span.kind", "openinference.span.kind")
IN = ("input.value", "gen_ai.input.messages")
OUT = ("output.value", "gen_ai.output.messages")
MODEL = ("gen_ai.request.model", "gen_ai.response.model", "llm.model_name")
TOKENS = ("gen_ai.usage.input_tokens", "llm.token_count.prompt")
COST = ("gen_ai.cost.total", "llm.cost.total")
SESSION = ("session.id", "fi.session.id")
USER = ("user.id", "fi.user.id")


def first(attrs, names):
    for n in names:
        if attrs.get(n) not in (None, "", [], {}):
            return attrs[n]
    return None


def put(kind, ok, detail):
    os.makedirs(DIR, exist_ok=True)
    p = os.path.join(DIR, kind + ".json")
    json.dump({"ok": bool(ok), "detail": detail, "at": int(time.time())}, open(p, "w"), default=str)


def get(kind):
    try:
        return json.load(open(os.path.join(DIR, kind + ".json")))
    except Exception:
        return {"ok": False, "detail": "no " + kind + " receipt"}


def clip(raw):                    # a 404 answers with an HTML page; one line of it is plenty
    t = " ".join(raw.decode("utf-8", "replace").split())
    return (t[:110] + "...") if len(t) > 110 else t


def send(key, secret, project, auth=True, slash=False):
    now = int(time.time())
    span = {"traceId": "4bf92f3577b34da6a3ce929d0e0e4736", "spanId": "00f067aa0ba902b7",
            "name": "futureagi.preflight", "kind": 1,
            "startTimeUnixNano": str(now) + "000000000",
            "endTimeUnixNano": str(now + 1) + "000000000"}
    res = [{"key": "project_name", "value": {"stringValue": project}},
           {"key": "project_type", "value": {"stringValue": "observe"}}]
    body = {"resourceSpans": [{"resource": {"attributes": res},
                               "scopeSpans": [{"spans": [span]}]}]}
    head = {"Content-Type": "application/json"}
    if auth:
        head["X-Api-Key"] = key
        head["X-Secret-Key"] = secret
    req = urllib.request.Request(EP + ("/" if slash else ""),
                                 data=json.dumps(body).encode(), headers=head)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, clip(r.read())
    except urllib.error.HTTPError as e:
        return e.code, clip(e.read())
    except Exception as e:
        return 0, type(e).__name__ + ": " + str(e)


def preflight():
    """One real send plus three broken controls. Writes the receipt check() reads as G1."""
    key, secret = os.getenv("FI_API_KEY"), os.getenv("FI_SECRET_KEY")
    project = os.getenv("FI_PROJECT_NAME") or "preflight"
    if not key or not secret:
        put("preflight", False, "FI_API_KEY and FI_SECRET_KEY are not both set")
        return False, ["FI_API_KEY and FI_SECRET_KEY are not both set."]
    code, body = send(key, secret, project)
    out = ["keys            HTTP " + str(code) + "  " + body]
    if code != 200:
        c, b = send(key, secret, project, auth=False)
        out.append("no headers      HTTP " + str(c) + "  " + b)
        out.append(WHY.get(code, "unexpected status; the body above is the collector's."))
        put("preflight", False, {"http": code, "body": body})
        return False, out
    for label, k, kw in (("wrong key   ", key[:-4] + "0000", {}),
                         ("no headers  ", key, {"auth": False}),
                         ("trailing slash", key, {"slash": True})):
        c, b = send(k, secret, project, **kw)
        out.append(label + "  HTTP " + str(c) + "  " + b)
        if c == 200:
            put("preflight", False, {"accepted_control": label.strip()})
            out.append("a deliberately broken send was accepted, so nothing here is proven.")
            return False, out
    out.append("accepted with the keys, refused every broken variant.")
    put("preflight", True, {"http": 200, "project": project, "endpoint": EP})
    return True, out


WHY = {401: "the keys reached the collector and were refused: wrong keys, or keys from"
            " another environment. The headerless send above answering 'missing"
            " credentials' shows the headers do arrive, so this is the values, not a proxy.",
       400: "the keys are fine and the payload is not. The body names the field.",
       404: "wrong path. It ends /tracer/v1/traces, with no trailing slash.",
       0: "the endpoint was not reachable at all. Proxy, firewall or DNS."}


def attach(provider, path=None):
    """Copy spans to a local file, and record what the collector said about the real batch.

    The provider drops its processors on the first add_span_processor call, which would
    remove the exporter register() installed: delivery stops, offline gates keep passing.
    A local file shows a span's shape, never its arrival, so the exporter is wrapped too.
    """
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    path = path or SPANS
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").close()
    for proc in getattr(provider._active_span_processor, "_span_processors", ()):
        if getattr(proc, "span_exporter", None) is not None:
            _watch(proc.span_exporter)
    if getattr(provider, "_default_processor", False):
        provider._default_processor = False   # keep the exporter register() installed
    provider.add_span_processor(SimpleSpanProcessor(_Tee(path)))
    return path


def _watch(exporter):
    real = exporter.export
    tally = {"accepted": 0, "refused": 0, "spans": 0, "by": type(exporter).__name__}

    def export(spans):
        result = real(spans)
        ok = str(result).endswith("SUCCESS")
        tally["accepted" if ok else "refused"] += 1
        tally["spans"] += len(spans) if ok else 0
        put("delivery", tally["accepted"] > 0 and tally["refused"] == 0, tally)
        return result

    exporter.export = export


class _Tee:                       # writes exported spans to a local file, verification only
    def __init__(self, path):
        self.path = path

    def export(self, spans):
        from opentelemetry.sdk.trace.export import SpanExportResult
        rows = [self.row(s) for s in spans]
        with open(self.path, "a") as fh:
            fh.write("".join(json.dumps(r, default=str) + "\n" for r in rows))
        return SpanExportResult.SUCCESS

    def row(self, s):
        c = s.get_span_context()
        return {"name": s.name, "trace_id": format(c.trace_id, "032x"),
                "span_id": format(c.span_id, "016x"),
                "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
                "attrs": dict(s.attributes or {}),
                "resource": dict(s.resource.attributes or {})}

    def shutdown(self):
        return None

    def force_flush(self, timeout_millis=30000):
        return True


def check(path=None, require_user=True):
    """The ten gates. Returns (green, rows). Green means all ten, never nine."""
    path = path or SPANS
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False, [("G0", False, "no spans captured, so the traced path never ran")]
    spans = [json.loads(l) for l in open(path) if l.strip()]
    res = spans[0]["resource"]
    ids = set(s["span_id"] for s in spans)
    traces = set(s["trace_id"] for s in spans)
    roots = [s for s in spans if not s["parent_id"]]
    orphans = [s for s in spans if s["parent_id"] and s["parent_id"] not in ids]
    llm = [s for s in spans if str(first(s["attrs"], KIND) or "").upper() == "LLM"]
    untyped = [s["name"] for s in spans if not first(s["attrs"], KIND)]
    root = roots[0] if roots else {"attrs": {}}
    sess = set(first(s["attrs"], SESSION) for s in spans)
    users = set(first(s["attrs"], USER) for s in spans)
    thin = [s["name"] for s in llm if not (first(s["attrs"], IN) and first(s["attrs"], OUT))]
    nomodel = [s["name"] for s in llm if not first(s["attrs"], MODEL)]
    cost = first(root["attrs"], COST)
    counted = llm and all(first(s["attrs"], TOKENS) is not None for s in llm)
    rolled = first(root["attrs"], TOKENS) is not None
    # G1 is read back from two receipts, never assumed. Without it the other nine only say
    # the spans are well formed on this machine, which is not an integration.
    pre, deliver = get("preflight"), get("delivery")
    keys = [v for k, v in os.environ.items() if len(v) > 15
            and any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    leaked = sorted(set(s["name"] for s in spans
                        if any(x in json.dumps(s["attrs"], default=str) for x in keys)))
    rows = [
        ("G1", pre["ok"] and deliver["ok"],
         "preflight " + ok_or(pre) + ", delivery " + ok_or(deliver)),
        ("G2", bool(res.get("project_name")),
         "project_name=" + repr(res.get("project_name")) +
         " project_type=" + repr(res.get("project_type"))),
        ("G3", len(roots) == 1 and len(traces) == 1 and not orphans,
         "%d spans, %d trace(s), %d root(s), %d orphan(s)"
         % (len(spans), len(traces), len(roots), len(orphans))),
        ("G4", bool(llm) and not untyped,
         "%d LLM span(s), %d untyped %s" % (len(llm), len(untyped), untyped[:3] or "")),
        ("G5", bool(llm) and not thin,
         "prompt and completion on every LLM span" if not thin else "empty on " + str(thin[:3])),
        ("G6", len(sess) == 1 and None not in sess, "session.id=" + str(sorted(map(str, sess)))),
        ("G7", (not require_user) or None not in users,
         "user.id=" + str(sorted(map(str, users)))),
        ("G8", bool(llm) and not nomodel,
         "model on every LLM span" if not nomodel else "missing on " + str(nomodel[:3])),
        # Cost is what the trace list is read for and the one most often missing. It is not
        # computed for you, and a zero is not a cost, so a zero does not pass.
        ("G9", bool(counted and rolled and isinstance(cost, (int, float)) and cost > 0),
         "tokens and cost on LLM spans, rolled up onto the root; root cost=" + str(cost)),
        ("G10", not leaked, "no credential in any span attribute" if not leaked
         else "CREDENTIAL ON SPAN " + str(leaked)),
    ]
    return all(ok for _, ok, _ in rows), rows


def ok_or(receipt):
    return "ok" if receipt["ok"] else str(receipt["detail"])[:50]


if __name__ == "__main__":
    if (sys.argv[1:2] or ["check"])[0] == "preflight":
        good, said = preflight()
        print("\n" + "\n".join("  " + l for l in said))
        print("\n  " + ("PASS" if good else "FAIL") + "  G1   keys and route")
        sys.exit(0 if good else 1)
    green, rows = check()
    print()
    for gid, ok, msg in rows:
        print("  %s  %-4s %s" % ("PASS" if ok else "FAIL", gid, msg))
    print("\n  Future AGI integrated\n  GREEN LIGHT achieved" if green
          else "\n  NOT GREEN. The FAIL rows name what is missing.")
    sys.exit(0 if green else 1)
