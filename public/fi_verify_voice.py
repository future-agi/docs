"""fi_verify_voice - checks a Future AGI voice integration against what the collector really received.

    python fi_verify_voice.py preflight    closes V1, before any code is touched
    python fi_verify_voice.py check        all twelve gates, after one real call

A voice call is not a trace with audio in it. The product finds a call with six
predicates at once, and a span that misses any of them is invisible in the Voice
tab no matter how healthy it looks in Traces. These gates are those predicates
plus the attributes the call list, the filters and the voice evals read.

Python 3.11+. Standard library only: nothing to install.
"""
import json, os, re, sys, time, urllib.error, urllib.request

EP = os.getenv("FI_ENDPOINT", "https://api.futureagi.com/tracer/v1/traces")
SPANS = os.getenv("FI_VERIFY_FILE", ".fi_verify/voice_spans.jsonl")
DIR = os.path.dirname(SPANS) or "."

# Two spellings are read for each: the Future AGI SDK writes the first, a plain
# OpenTelemetry setup writes the second.
KIND = ("gen_ai.span.kind", "fi.span.kind", "openinference.span.kind", "llm.request.type")
IN = ("input.value", "gen_ai.input.messages")
OUT = ("output.value", "gen_ai.output.messages")
MODEL = ("gen_ai.request.model", "gen_ai.response.model", "llm.model_name")
SESSION = ("session.id", "fi.session.id")
USER = ("user.id", "fi.user.id")

# The voice keys. Every one of these is read by name on the server side, so a
# near miss is a silent blank column rather than an error.
DURATION = "call.duration"
TURNS = "call.total_turns"
TALK = "call.talk_ratio"
TRANSCRIPT = "conversation.transcript"          # the one the eval resolver reads
RENDERED = "fi.conversation.transcript"         # the one the call drawer renders
TRANSCRIPT_ROW = re.compile(r"^conversation\.transcript\.(\d+)\.message\.(role|content)$")
PROVIDER = ("gen_ai.system", "gen_ai.provider.name", "llm.system")
# Recording aliases the eval resolver will follow. Anything else is unreachable.
RECORDING = ("conversation.recording.stereo", "conversation.recording.mono.combined",
             "conversation.recording.mono.customer", "conversation.recording.mono.assistant",
             "gen_ai.voice.recording.stereo_url", "gen_ai.voice.recording.url",
             "gen_ai.voice.recording.customer_url", "gen_ai.voice.recording.assistant_url",
             "stereo_recording_url", "voice_recording_url", "recording_url")


def first(attrs, names):
    for n in names:
        if attrs.get(n) not in (None, "", [], {}):
            return attrs[n]
    return None


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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
    """One conversation-shaped span. Not a generic ping: this is the exact shape the
    Voice tab selects for, so a 200 here proves the voice path, not just the route."""
    now = int(time.time())
    attrs = [{"key": "fi.span.kind", "value": {"stringValue": "CONVERSATION"}},
             {"key": "call.duration", "value": {"doubleValue": 1.0}}]
    span = {"traceId": "4bf92f3577b34da6a3ce929d0e0e4736", "spanId": "00f067aa0ba902b7",
            "name": "futureagi.voice.preflight", "kind": 1, "attributes": attrs,
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
    """One real send plus three broken controls. Writes the receipt check() reads as V1."""
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
    flip = "0000" if not key.endswith("0000") else "1111"   # never hand back the real key
    for label, k, kw in (("wrong key   ", key[:-4] + flip, {}),
                         ("no headers  ", key, {"auth": False}),
                         ("trailing slash", key, {"slash": True})):
        c, b = send(k, secret, project, **kw)
        out.append(label + "  HTTP " + str(c) + "  " + b)
        if c == 200:
            put("preflight", False, {"accepted_control": label.strip()})
            out.append("a deliberately broken send was accepted, so nothing here is proven.")
            return False, out
    out.append("accepted with the keys, refused every broken variant.")
    out.append("one call named futureagi.voice.preflight is now in the project's Voice tab.")
    put("preflight", True, {"http": 200, "project": project, "endpoint": EP})
    return True, out


WHY = {401: "the keys reached the collector and were refused: wrong keys, or keys from"
            " another environment. The headerless send above answering 'missing"
            " credentials' shows the headers do arrive, so this is the values, not a proxy.",
       400: "the keys are fine and the payload is not. The body names the field.",
       404: "wrong path. It ends /tracer/v1/traces, with no trailing slash.",
       0: "the endpoint was not reachable at all. Proxy, firewall or DNS."}


def attach(provider, path=None):
    """Capture every span at the exporter, after export, and record what the collector said.

    Not a span processor. A voice instrumentor rewrites its attributes inside the
    exporter (traceai-livekit sets span._attributes in export()), so a processor
    tee captures the span BEFORE the rewrite and reports on something that was
    never sent. Wrapping export and reading the spans back after the real call
    returns is the only place the attributes are final.

    Call this AFTER enable_http_attribute_mapping(), which swaps the exporter
    instance. Called before, it wraps the exporter that is about to be discarded.
    """
    path = path or SPANS
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").close()
    active = getattr(provider, "_active_span_processor", None)
    procs = list(getattr(active, "_span_processors", ())) or ([active] if active else [])
    wrapped = []
    for proc in procs:
        exp = getattr(proc, "span_exporter", None) or getattr(proc, "_exporter", None)
        if exp is not None and not getattr(exp, "_fi_voice_wrapped", False):
            _wrap(exp, path)
            wrapped.append(type(exp).__name__)
    put("capture", bool(wrapped), {"exporters": wrapped})
    return path


def _wrap(exporter, path):
    real = exporter.export
    tally = {"accepted": 0, "refused": 0, "spans": 0, "by": type(exporter).__name__}

    def export(spans):
        result = real(spans)                       # the rewrite and the send both happen in here
        ok = str(result).endswith("SUCCESS")
        tally["accepted" if ok else "refused"] += 1
        tally["spans"] += len(spans) if ok else 0
        put("delivery", tally["accepted"] > 0 and tally["refused"] == 0, tally)
        with open(path, "a") as fh:
            fh.write("".join(json.dumps(_row(s), default=str) + "\n" for s in spans))
        return result

    exporter.export = export
    exporter._fi_voice_wrapped = True


def _row(s):
    c = s.get_span_context()
    return {"name": s.name, "trace_id": format(c.trace_id, "032x"),
            "span_id": format(c.span_id, "016x"),
            "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
            "attrs": dict(s.attributes or {}),
            "resource": dict(s.resource.attributes or {})}


def transcript_rows(attrs):
    """The flattened transcript the call detail reads back, as {index: {role, content}}."""
    rows = {}
    for k, v in attrs.items():
        m = TRANSCRIPT_ROW.match(k)
        if m:
            rows.setdefault(int(m.group(1)), {})[m.group(2)] = v
    return rows


def check(path=None, require_user=True, require_recording=None):
    """The twelve gates. Returns (green, rows). Green means all twelve, never eleven."""
    path = path or SPANS
    if require_recording is None:
        require_recording = os.getenv("FI_VOICE_NO_RECORDING", "") not in ("1", "true", "TRUE")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False, [("V0", False, "no spans captured, so the call never ran or attach() was not called")]
    spans = [json.loads(l) for l in open(path) if l.strip()]
    res = spans[0]["resource"]
    ids = set(s["span_id"] for s in spans)
    traces = set(s["trace_id"] for s in spans)
    roots = [s for s in spans if not s["parent_id"]]
    orphans = [s for s in spans if s["parent_id"] and s["parent_id"] not in ids]
    convs = [s for s in spans if str(first(s["attrs"], KIND) or "").upper() == "CONVERSATION"]
    parented = [s["name"] for s in convs if s["parent_id"]]
    root = convs[0] if convs else {"attrs": {}, "name": None}
    a = root["attrs"]
    llm = [s for s in spans if str(first(s["attrs"], KIND) or "").upper() == "LLM"]
    # Content and usage live on different LLM spans by design: a voice instrumentor
    # emits an outer node carrying the prompt and the completion and an inner
    # provider call carrying the tokens. So: a model on every one of them, and the
    # conversation content on at least one.
    withio = [s["name"] for s in llm if first(s["attrs"], IN) and first(s["attrs"], OUT)]
    nomodel = [s["name"] for s in llm if not first(s["attrs"], MODEL)]

    rows_t = transcript_rows(a)
    complete = [i for i, r in sorted(rows_t.items()) if r.get("role") and r.get("content")]
    single = a.get(TRANSCRIPT)
    rendered = a.get(RENDERED)
    recs = {k: a[k] for k in RECORDING if a.get(k) not in (None, "", [], {})}
    badrec = [k for k, v in recs.items() if not isinstance(v, str)]

    pre, deliver = get("preflight"), get("delivery")
    keys = [v for k, v in os.environ.items() if len(v) > 15
            and any(t in k.upper() for t in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]
    leaked = sorted(set(s["name"] for s in spans
                        if any(x in json.dumps(s["attrs"], default=str) for x in keys)))
    rows = [
        ("V1", pre["ok"] and deliver["ok"],
         "preflight " + ok_or(pre) + ", delivery " + ok_or(deliver)),
        ("V2", bool(res.get("project_name")),
         "project_name=" + repr(res.get("project_name")) +
         " project_type=" + repr(res.get("project_type"))),
        ("V3", len(convs) == 1 and not parented,
         "%d conversation span(s)%s" % (len(convs),
          "" if not parented else ", and %s has a parent, so the Voice tab will not list it"
          % parented[:1]) if convs else
         "no conversation span: the call is in Traces and nowhere in the Voice tab"),
        ("V4", len(roots) == 1 and len(traces) == 1 and not orphans,
         "%d spans, %d trace(s), %d root(s), %d orphan(s)"
         % (len(spans), len(traces), len(roots), len(orphans))),
        ("V5", bool(first(a, SESSION)) and ((not require_user) or bool(first(a, USER))),
         "session.id=%r user.id=%r on the conversation span"
         % (first(a, SESSION), first(a, USER))),
        ("V6", num(a.get(DURATION)),
         "call.duration=%r" % (a.get(DURATION),) if DURATION in a
         else "call.duration absent: the Duration column and the duration filter read nothing"),
        ("V7", num(a.get(TURNS)) and num(a.get(TALK)),
         "call.total_turns=%r call.talk_ratio=%r" % (a.get(TURNS), a.get(TALK))),
        ("V8", len(complete) >= 2 and bool(single) and bool(rendered),
         "%d turn(s) flattened; conversation.transcript %s; fi.conversation.transcript %s"
         % (len(complete), "present" if single else "ABSENT, no voice eval can bind to it",
            "present" if rendered else "ABSENT, the call drawer will show no transcript")),
        ("V9", bool(first(a, PROVIDER)),
         "provider=%r" % (first(a, PROVIDER),) if first(a, PROVIDER)
         else "no gen_ai.system: the server parses the call as Vapi by default"),
        ("V10", (bool(recs) and not badrec) or not require_recording,
         ("no recording attribute, acknowledged: audio evals cannot bind to this call"
          if not recs and not require_recording else
          "recording on %s" % sorted(recs) if recs and not badrec else
          "not a string URL: %s" % badrec if badrec else
          "no recording attribute under any alias the eval resolver follows")),
        ("V11", bool(llm) and bool(withio) and not nomodel,
         "%d LLM span(s), model on every one, prompt and completion on %s"
         % (len(llm), withio[:2]) if llm and withio and not nomodel else
         "%d LLM span(s); prompt and completion on none of them; no model on %s"
         % (len(llm), nomodel[:3])),
        ("V12", not leaked, "no credential in any span attribute" if not leaked
         else "CREDENTIAL ON SPAN " + str(leaked)),
    ]
    return all(ok for _, ok, _ in rows), rows


def ok_or(receipt):
    return "ok" if receipt["ok"] else str(receipt["detail"])[:50]


if __name__ == "__main__":
    if (sys.argv[1:2] or ["check"])[0] == "preflight":
        good, said = preflight()
        print("\n" + "\n".join("  " + l for l in said))
        print("\n  " + ("PASS" if good else "FAIL") + "  V1   keys, route and the voice shape")
        sys.exit(0 if good else 1)
    green, rows = check()
    print()
    for gid, ok, msg in rows:
        print("  %s  %-4s %s" % ("PASS" if ok else "FAIL", gid, msg))
    print("\n  Future AGI sees this as a call\n  GREEN LIGHT achieved" if green
          else "\n  NOT GREEN. The FAIL rows name what is missing.")
    sys.exit(0 if green else 1)
