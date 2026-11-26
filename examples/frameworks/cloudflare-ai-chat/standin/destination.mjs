#!/usr/bin/env node
// STANDIN for Cloudflare's Workers OTLP traces destination. Local verification only; never deploy this.
//
// In production Cloudflare exports your Worker's spans to the destination itself. `wrangler dev` has no
// destinations, but it does capture the same runtime spans (workerd's tracing, including every custom span the
// Agents SDK creates) into its Local Explorer trace store. This script reads those spans and POSTs them as
// OTLP/HTTP JSON to the collector, with the bearer token a destination custom header would carry.
//
// Real:     the spans (names, parents, timings, attributes) come from workerd running the Worker.
// Assumed:  the envelope Cloudflare's exporter wraps around them: resource attributes (only service.name here),
//           scope name, span kind mapping, status for a failed invocation, batching. Cloudflare documents none
//           of these; check them against a real destination before relying on them.
//
//   node standin/destination.mjs --explorer http://127.0.0.1:8787 --endpoint http://127.0.0.1:4318/v1/traces \
//        [--since-ms <epoch ms>] [--dump rows.json] [--from-dump rows.json]   (token from env CF_DESTINATION_TOKEN)
//
// Prints counts only (never attribute values). Exit 0 when every POST got 2xx.

const SERVER_KINDS = new Set(["http", "websocket", "jsrpc", "scheduled", "queue", "email", "alarm", "trace", "worker"]);
const CLIENT_KINDS = new Set(["fetch", "do"]);

export function anyValue(v) {
  if (typeof v === "boolean") return { boolValue: v };
  if (typeof v === "number") return Number.isInteger(v) ? { intValue: String(v) } : { doubleValue: v };
  if (v === null || v === undefined) return { stringValue: "" };
  if (typeof v === "string") return { stringValue: v };
  return { stringValue: JSON.stringify(v) };
}

export function spanKind(kind) {
  if (SERVER_KINDS.has(kind)) return 2; // SPAN_KIND_SERVER
  if (CLIENT_KINDS.has(kind)) return 3; // SPAN_KIND_CLIENT
  return 1; // SPAN_KIND_INTERNAL
}

const ms2ns = (ms) => (BigInt(Math.round(ms)) * 1_000_000n).toString();

/** Local Explorer rows -> one OTLP ExportTraceServiceRequest (JSON encoding). */
export function rowsToOtlp(rows) {
  const byService = new Map();
  for (const r of rows) {
    if (r.duration_ms === null || r.duration_ms === undefined) continue; // still open: not exported
    const attrs = typeof r.attributes === "string" ? JSON.parse(r.attributes || "{}") : r.attributes || {};
    const span = {
      traceId: r.trace_id,
      spanId: r.span_id,
      name: r.name,
      kind: spanKind(r.kind),
      startTimeUnixNano: ms2ns(r.start_ms),
      endTimeUnixNano: ms2ns(r.start_ms + r.duration_ms),
      attributes: Object.entries(attrs).map(([key, value]) => ({ key, value: anyValue(value) })),
      status: r.outcome && r.outcome !== "ok" ? { code: 2, message: r.error || r.outcome } : { code: 0 },
    };
    if (r.parent_id) span.parentSpanId = r.parent_id;
    const svc = r.service || "worker";
    if (!byService.has(svc)) byService.set(svc, []);
    byService.get(svc).push(span);
  }
  return {
    resourceSpans: [...byService.entries()].map(([svc, spans]) => ({
      resource: { attributes: [{ key: "service.name", value: { stringValue: svc } }] },
      scopeSpans: [{ scope: { name: "standin-local-explorer" }, spans }],
    })),
  };
}

export function chunk(req, size) {
  const out = [];
  for (const rs of req.resourceSpans) {
    const spans = rs.scopeSpans[0].spans;
    for (let i = 0; i < spans.length; i += size) {
      out.push({ resourceSpans: [{ ...rs, scopeSpans: [{ ...rs.scopeSpans[0], spans: spans.slice(i, i + size) }] }] });
    }
  }
  return out;
}

export async function readRows(explorer, sinceMs = 0, fetchImpl = fetch) {
  const sql =
    "SELECT trace_id, span_id, parent_id, service, name, kind, start_ms, duration_ms, outcome, error, " +
    `json(attributes) AS attributes FROM spans WHERE start_ms >= ${Math.max(0, Math.floor(Number(sinceMs) || 0))} ORDER BY start_ms`;
  const res = await fetchImpl(`${explorer.replace(/\/+$/, "")}/cdn-cgi/local/explorer/api/local/observability/query`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ sql }),
  });
  const body = await res.json();
  if (!body.success) throw new Error(`local explorer query failed: ${JSON.stringify(body.errors).slice(0, 200)}`);
  const { columns, rows } = body.result;
  return rows.map((r) => Object.fromEntries(columns.map((c, i) => [c, r[i]])));
}

function arg(name, dflt) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : dflt;
}

async function main() {
  const explorer = arg("explorer", "http://127.0.0.1:8787");
  const endpoint = arg("endpoint");
  const since = Number(arg("since-ms", "0"));
  const token = process.env.CF_DESTINATION_TOKEN;
  if (!endpoint) throw new Error("--endpoint is required");
  const fromDump = arg("from-dump");
  const rows = fromDump
    ? JSON.parse((await import("node:fs")).readFileSync(fromDump, "utf8"))
    : await readRows(explorer, since);
  const dump = arg("dump");
  if (dump) (await import("node:fs")).writeFileSync(dump, JSON.stringify(rows, null, 1));
  const req = rowsToOtlp(rows);
  const batches = chunk(req, 200);
  let spans = 0, failed = 0;
  const traces = new Set();
  for (const b of batches) {
    const res = await fetch(endpoint, {
      method: "POST",
      // Plain JSON, no Content-Encoding: Cloudflare does not use the binary encoding, and gzip is not simulated.
      headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(b),
    });
    const n = b.resourceSpans[0].scopeSpans[0].spans.length;
    if (res.ok) {
      spans += n;
      for (const s of b.resourceSpans[0].scopeSpans[0].spans) traces.add(s.traceId);
    } else failed += 1;
    console.log(`POST ${n} spans -> HTTP ${res.status}`);
  }
  console.log(JSON.stringify({ rows: rows.length, exported_spans: spans, failed_posts: failed, trace_ids: [...traces] }));
  process.exit(failed ? 1 : 0);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => {
    console.error(String(e && e.message ? e.message : e).slice(0, 300));
    process.exit(2);
  });
}
