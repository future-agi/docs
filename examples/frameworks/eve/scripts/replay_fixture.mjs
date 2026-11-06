// Replay the recorded eve trace fixture to a Future AGI collector as OTLP/JSON.
// Each replay gets fresh trace and span ids and is shifted to the current time,
// so it shows up as new traces. No eve, no model.
//   FI_API_KEY=... FI_SECRET_KEY=... [FI_BASE_URL=...] [FI_PROJECT_NAME=...] \
//     node scripts/replay_fixture.mjs [test/fixtures/eve-0.80.0-turns.otlp.json]
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const DEFAULT_FIXTURE = fileURLToPath(new URL("../test/fixtures/eve-0.80.0-turns.otlp.json", import.meta.url));

/** A copy of the fixture with new ids, times moved to `nowNs`, and the project renamed. */
export function prepareReplay(fixture, { projectName, nowNs = BigInt(Date.now()) * 1_000_000n } = {}) {
  const req = structuredClone(fixture);
  const ids = new Map();
  const fresh = (old, bytes) => {
    if (!ids.has(old)) ids.set(old, randomBytes(bytes).toString("hex"));
    return ids.get(old);
  };
  const spans = req.resourceSpans.flatMap((rs) => rs.scopeSpans.flatMap((ss) => ss.spans));
  const latest = spans.reduce((m, s) => (BigInt(s.endTimeUnixNano) > m ? BigInt(s.endTimeUnixNano) : m), 0n);
  const shift = nowNs - latest;
  for (const s of spans) {
    s.traceId = fresh(s.traceId, 16);
    s.spanId = fresh(s.spanId, 8);
    if (s.parentSpanId) s.parentSpanId = fresh(s.parentSpanId, 8);
    s.startTimeUnixNano = String(BigInt(s.startTimeUnixNano) + shift);
    s.endTimeUnixNano = String(BigInt(s.endTimeUnixNano) + shift);
    for (const e of s.events ?? []) e.timeUnixNano = String(BigInt(e.timeUnixNano) + shift);
  }
  if (projectName) {
    for (const rs of req.resourceSpans) {
      const attr = rs.resource.attributes.find((a) => a.key === "project_name");
      attr.value = { stringValue: projectName };
    }
  }
  return { request: req, traceIds: [...new Set(spans.map((s) => s.traceId))] };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const fixture = JSON.parse(readFileSync(process.argv[2] ?? DEFAULT_FIXTURE, "utf8"));
  const { request, traceIds } = prepareReplay(fixture, { projectName: process.env.FI_PROJECT_NAME || undefined });
  const base = (process.env.FI_BASE_URL || "https://api.futureagi.com").replace(/\/+$/, "");
  const res = await fetch(`${base}/tracer/v1/traces`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Api-Key": process.env.FI_API_KEY ?? "",
      "X-Secret-Key": process.env.FI_SECRET_KEY ?? "",
    },
    body: JSON.stringify(request),
  });
  console.log(JSON.stringify({ status: res.status, body: (await res.text()).slice(0, 300), traceIds }));
  process.exit(res.ok ? 0 : 1);
}
