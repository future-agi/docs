// Build test/fixtures/flue-2.3.0-turns.otlp.json from a real run_e2e.sh recording.
// Keeps the content-off tool-call, tool-failure and model-failure runs, re-decoded
// from the raw .bin bodies; replaces trace, span, Flue and provider ids, the
// model id, the model endpoint and the project name. Nothing else is changed.
//   node scripts/make_fixture.mjs <evidence-dir> <out.json>
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { decodeTraceRequest } from "./otlp-decode.mjs";

const [evDir, outPath] = process.argv.slice(2);
const readEnvelope = (name) => JSON.parse(readFileSync(join(evDir, `${name}.json`), "utf8").trim().split("\n").pop());
const keep = new Set(["off.ok", "off.toolerr", "model.err"].map((n) => readEnvelope(n).submissionId));

const wire = join(evDir, "wire");
const spans = readdirSync(wire).filter((f) => f.endsWith(".bin")).sort()
  .flatMap((f) => decodeTraceRequest(readFileSync(join(wire, f))))
  .filter((s) => keep.has(s.attributes["flue.submission.id"]));

const ids = new Map();
const fake = (kind, real, len) => {
  const k = `${kind}:${real}`;
  if (!ids.has(k)) {
    const n = [...ids.keys()].filter((x) => x.startsWith(`${kind}:`)).length + 1;
    ids.set(k, len ? n.toString(16).padStart(len, "0").replace(/^0/, "a") : `${kind}_${String(n).padStart(4, "0")}`);
  }
  return ids.get(k);
};
const MODEL = "gpt-6-luna";
const REPLACE = {
  "flue.instance.id": "instance", "flue.submission.id": "sub", "flue.operation.id": "op", "flue.turn.id": "turn",
  "gen_ai.conversation.id": "conv", "gen_ai.response.id": "resp", "gen_ai.tool.call.id": "call",
};
const scrub = (key, v) => {
  if (typeof v === "string") {
    if (REPLACE[key]) return fake(REPLACE[key], v);
    if (key === "gen_ai.provider.name") return "example-provider";
    if (key === "server.address") return "llm.example.com";
    return v.replaceAll(MODEL, "example-model");
  }
  if (key === "server.port") return 443;
  return v;
};
const anyValue = (v) => {
  if (typeof v === "string") return { stringValue: v };
  if (typeof v === "boolean") return { boolValue: v };
  if (typeof v === "number") return Number.isInteger(v) ? { intValue: String(v) } : { doubleValue: v };
  if (Array.isArray(v)) return { arrayValue: { values: v.map(anyValue) } };
  throw new Error(`unsupported value ${JSON.stringify(v)}`);
};
const kvs = (o) => Object.entries(o).sort(([a], [b]) => a.localeCompare(b)).map(([key, v]) => ({ key, value: anyValue(scrub(key, v)) }));

const { resource, scope } = spans[0];
const out = {
  resourceSpans: [{
    resource: { attributes: kvs({ ...resource, project_name: "flue-fixture", "service.name": "flue-futureagi-example" }) },
    scopeSpans: [{
      scope: { name: scope.name, version: scope.version },
      spans: spans.map((s) => ({
        traceId: fake("trace", s.traceId, 32),
        spanId: fake("span", s.spanId, 16),
        ...(s.parentSpanId ? { parentSpanId: fake("span", s.parentSpanId, 16) } : {}),
        name: s.name.replaceAll(MODEL, "example-model"),
        kind: s.kind,
        startTimeUnixNano: String(s.startTimeUnixNano),
        endTimeUnixNano: String(s.endTimeUnixNano),
        attributes: kvs(s.attributes),
        events: s.events.map((e) => ({ name: e.name, timeUnixNano: String(e.timeUnixNano), attributes: kvs(e.attributes) })),
        status: s.status.code ? { code: s.status.code, ...(s.status.message ? { message: s.status.message } : {}) } : {},
      })),
    }],
  }],
};
writeFileSync(outPath, JSON.stringify(out, null, 1) + "\n");
console.log(`wrote ${spans.length} spans from ${keep.size} runs to ${outPath}`);
