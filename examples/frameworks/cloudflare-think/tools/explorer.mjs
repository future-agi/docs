// Helpers for the local-dev half of the end-to-end test. Not part of the recipe.
//
// `wrangler dev` records every span of every local invocation in the Local Explorer
// (`/cdn-cgi/local/explorer/api/local/observability/query`, read-only SQL over a `spans` table).
// Local dev does NOT export to Workers Observability destinations: those exist only in the
// Cloudflare dashboard. So the test reads the real spans that Think emitted from the Local Explorer,
// and `standin_destination.mjs` posts them as OTLP/HTTP JSON, standing in for Cloudflare's exporter.

export const EXPLORER_QUERY_PATH = "/cdn-cgi/local/explorer/api/local/observability/query";
export const EXPLORER_CLEAR_PATH = "/cdn-cgi/local/explorer/api/local/observability/clear";

// The four payload attributes Think writes when storeMessages / storeTools are true
// (https://developers.cloudflare.com/agents/runtime/operations/observability/tracing/#payload-privacy).
export const PAYLOAD_KEYS = [
  "gen_ai.input.messages",
  "gen_ai.output.messages",
  "gen_ai.system_instructions",
  "gen_ai.tool.call.arguments",
  "gen_ai.tool.call.result",
];

const SPAN_COLUMNS =
  "trace_id, span_id, parent_id, service, name, kind, start_ms, duration_ms, outcome, error, json(attributes) AS attributes";

/** Runs one read-only SQL query against the Local Explorer and returns row objects. */
export async function query(base, sql, fetchImpl = fetch) {
  const res = await fetchImpl(new URL(EXPLORER_QUERY_PATH, base), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ sql }),
  });
  if (!res.ok) throw new Error(`Local Explorer query failed: HTTP ${res.status}`);
  const body = await res.json();
  if (!body.success) throw new Error(`Local Explorer query failed: ${JSON.stringify(body.errors).slice(0, 200)}`);
  const { columns, rows } = body.result;
  return rows.map((r) => Object.fromEntries(columns.map((c, i) => [c, r[i]])));
}

/** Every recorded span, oldest first, attributes parsed. Pages through the store. */
export async function readSpans(base, fetchImpl = fetch, pageSize = 1000) {
  const out = [];
  for (let offset = 0; ; offset += pageSize) {
    const page = await query(
      base,
      `SELECT ${SPAN_COLUMNS} FROM spans ORDER BY start_ms, span_id LIMIT ${pageSize} OFFSET ${offset}`,
      fetchImpl,
    );
    for (const row of page) {
      out.push({ ...row, attributes: typeof row.attributes === "string" ? JSON.parse(row.attributes) : row.attributes || {} });
    }
    if (page.length < pageSize) return out;
  }
}

export async function clear(base, fetchImpl = fetch) {
  const res = await fetchImpl(new URL(EXPLORER_CLEAR_PATH, base), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  if (!res.ok) throw new Error(`Local Explorer clear failed: HTTP ${res.status}`);
}

// ---------------------------------------------------------------- OTLP/HTTP JSON (the stand-in exporter)

function anyValue(v) {
  if (typeof v === "boolean") return { boolValue: v };
  if (typeof v === "number") return Number.isInteger(v) ? { intValue: String(v) } : { doubleValue: v };
  if (v === null || v === undefined) return { stringValue: "" };
  return { stringValue: typeof v === "string" ? v : JSON.stringify(v) };
}

function keyValues(obj) {
  return Object.entries(obj)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([key, v]) => ({ key, value: anyValue(v) }));
}

const SPAN_KIND = { INTERNAL: 1, SERVER: 2, CLIENT: 3 };

function spanKind(row) {
  if (row.kind === "http" && !row.parent_id) return SPAN_KIND.SERVER;
  if (row.kind === "fetch") return SPAN_KIND.CLIENT;
  return SPAN_KIND.INTERNAL;
}

const nanos = (ms) => (BigInt(Math.round(ms)) * 1_000_000n).toString();

/**
 * Converts Local Explorer rows to one OTLP/HTTP JSON request body (ExportTraceServiceRequest).
 * Resource attributes follow Cloudflare's documented "attributes available on all spans"
 * (service.name, cloud.provider, cloud.platform, faas.name, telemetry.sdk.*). Where Cloudflare's own
 * exporter puts them (resource or span) is not documented; the collector recipe does not depend on it.
 * Note what is NOT added: project_name. Cloudflare's destination cannot set it; the collector does.
 */
export function toOtlpJson(rows) {
  const byService = new Map();
  for (const row of rows) {
    const service = row.service || "worker";
    if (!byService.has(service)) byService.set(service, []);
    const span = {
      traceId: row.trace_id,
      spanId: row.span_id,
      parentSpanId: row.parent_id || "",
      name: row.name,
      kind: spanKind(row),
      startTimeUnixNano: nanos(row.start_ms),
      endTimeUnixNano: nanos(row.start_ms + (row.duration_ms || 0)),
      attributes: keyValues(row.attributes || {}),
      status: row.outcome && row.outcome !== "ok" ? { code: 2 } : { code: 0 },
    };
    if (row.error) {
      // An exception recorded by the runtime, in the OpenTelemetry exception-event shape.
      span.events = [
        {
          name: "exception",
          timeUnixNano: span.endTimeUnixNano,
          attributes: keyValues({ "exception.message": String(row.error) }),
        },
      ];
    }
    byService.get(service).push(span);
  }
  return {
    resourceSpans: [...byService.entries()].map(([service, spans]) => ({
      resource: {
        attributes: keyValues({
          "service.name": service,
          "faas.name": service,
          "cloud.provider": "cloudflare",
          "cloud.platform": "cloudflare.workers",
          "telemetry.sdk.language": "javascript",
          "telemetry.sdk.name": "cloudflare",
        }),
      },
      scopeSpans: [{ scope: { name: "cloudflare" }, spans }],
    })),
  };
}

/** Splits rows into request bodies of at most `max` spans, never splitting one trace across bodies when it fits. */
export function batches(rows, max = 500) {
  const traces = new Map();
  for (const r of rows) {
    if (!traces.has(r.trace_id)) traces.set(r.trace_id, []);
    traces.get(r.trace_id).push(r);
  }
  const out = [];
  let cur = [];
  for (const spans of traces.values()) {
    if (cur.length && cur.length + spans.length > max) {
      out.push(cur);
      cur = [];
    }
    for (const s of spans) {
      cur.push(s);
      if (cur.length >= max) {
        out.push(cur);
        cur = [];
      }
    }
  }
  if (cur.length) out.push(cur);
  return out;
}

// ---------------------------------------------------------------- the Think span-tree contract

/**
 * Checks the Think tree in Local Explorer rows. Returns {ok, turns, problems}.
 *   expect.payloads: "off" (no payload attribute anywhere) | "on" (chat spans carry messages, tools carry args)
 *   expect.tool: true when every turn must contain an execute_tool span
 *   expect.errorType: when set, some invoke_agent / chat / execute_tool span must carry this error.type
 *   expect.rootConversation: the trace root (the Worker request span) must carry the turn's gen_ai.conversation.id
 */
export function checkTree(rows, expect = {}) {
  const problems = [];
  const byId = new Map(rows.map((r) => [r.span_id, r]));
  const op = (r) => r.attributes?.["gen_ai.operation.name"];
  const turns = rows.filter((r) => op(r) === "invoke_agent");
  if (!turns.length) problems.push("no invoke_agent span: Think did not trace a turn (is observability.traces.enabled true?)");
  const summary = [];
  for (const t of turns) {
    const kids = rows.filter((r) => r.parent_id === t.span_id);
    const chats = kids.filter((r) => op(r) === "chat");
    const tools = kids.filter((r) => op(r) === "execute_tool");
    if (!t.name.startsWith("invoke_agent")) problems.push(`turn span named ${t.name}`);
    if (!chats.length) problems.push(`invoke_agent ${t.span_id} has no chat child`);
    if (expect.tool && !tools.length) problems.push(`invoke_agent ${t.span_id} has no execute_tool child`);
    for (const r of [t, ...chats]) {
      for (const k of ["gen_ai.agent.name", "gen_ai.conversation.id"]) {
        if (!r.attributes?.[k]) problems.push(`${r.name} ${r.span_id} lacks ${k}`);
      }
    }
    for (const c of chats) {
      if (!c.attributes?.["gen_ai.request.model"]) problems.push(`chat ${c.span_id} lacks gen_ai.request.model`);
    }
    // the turn must hang off the Worker request: walk up to a root
    let cur = t;
    const seen = new Set();
    while (cur.parent_id && byId.has(cur.parent_id) && !seen.has(cur.span_id)) {
      seen.add(cur.span_id);
      cur = byId.get(cur.parent_id);
    }
    if (cur.parent_id) problems.push(`invoke_agent ${t.span_id} is not connected to a root span`);
    if (expect.rootConversation && cur.attributes?.["gen_ai.conversation.id"] !== t.attributes?.["gen_ai.conversation.id"]) {
      problems.push(`root ${cur.name} ${cur.span_id} does not carry the turn's gen_ai.conversation.id`);
    }
    summary.push({ trace_id: t.trace_id, invoke_agent: t.span_id, root: cur.name, chats: chats.length, tools: tools.length });
  }
  const genai = rows.filter((r) => ["invoke_agent", "chat", "execute_tool"].includes(op(r)));
  if (expect.payloads === "off") {
    for (const r of rows) {
      for (const k of PAYLOAD_KEYS) if (k in (r.attributes || {})) problems.push(`payload ${k} on ${r.name} with payloads off`);
    }
  } else if (expect.payloads === "on") {
    const chats = genai.filter((r) => op(r) === "chat");
    const tools = genai.filter((r) => op(r) === "execute_tool");
    if (!chats.some((r) => r.attributes["gen_ai.input.messages"])) problems.push("payloads on, but no chat span has gen_ai.input.messages");
    if (!chats.some((r) => r.attributes["gen_ai.output.messages"])) problems.push("payloads on, but no chat span has gen_ai.output.messages");
    if (tools.length && !tools.some((r) => r.attributes["gen_ai.tool.call.arguments"])) problems.push("payloads on, but no execute_tool span has arguments");
  }
  if (expect.errorType && !genai.some((r) => r.attributes["error.type"] === expect.errorType)) {
    problems.push(`no GenAI span carries error.type=${expect.errorType}`);
  }
  return { ok: problems.length === 0, turns: summary, problems };
}
