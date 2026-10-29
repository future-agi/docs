// Checks what run_e2e.sh put on the wire (the recorder's copies of every OTLP
// request) and prints one PASS/FAIL line per check.
//   node scripts/check_wire.mjs <out-dir>
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const CONTENT_KEYS = [
  "gen_ai.input.messages",
  "gen_ai.output.messages",
  "gen_ai.system_instructions",
  "gen_ai.tool.definitions",
  "gen_ai.tool.call.arguments",
  "gen_ai.tool.call.result",
  "agent.session.title",
  "agent.principal.current.id",
  "agent.principal.initiator.id",
];

export function loadRun(out) {
  const wireDir = join(out, "wire");
  const files = readdirSync(wireDir).filter((f) => f.endsWith(".json")).sort();
  const requests = files.map((f) => {
    const meta = JSON.parse(readFileSync(join(wireDir, f), "utf8"));
    const raw = readFileSync(join(wireDir, f.replace(/\.json$/, ".bin")));
    return { file: f, meta, raw };
  });
  const markers = JSON.parse(readFileSync(join(out, "markers.json"), "utf8"));
  const invoke = (name) => {
    const p = join(out, `${name}.json`);
    if (!existsSync(p)) return null;
    const text = readFileSync(p, "utf8").trim();
    return text ? JSON.parse(text.split("\n").pop()) : null;
  };
  return { requests, markers, invoke };
}

/** Pure checks over a loaded run. Returns [{ ok, name, detail }]. */
export function checkRun({ requests, markers, invoke }) {
  const results = [];
  const check = (name, ok, detail = "") => results.push({ ok: Boolean(ok), name, detail });
  const spans = requests.flatMap((r) => r.meta.spans);
  const byTrace = new Map();
  for (const s of spans) byTrace.set(s.traceId, [...(byTrace.get(s.traceId) ?? []), s]);
  const trace = (id) => (id ? byTrace.get(id) ?? [] : []);
  const bodyHas = (marker, traceIds) =>
    requests.some((r) => r.meta.spans.some((s) => traceIds.includes(s.traceId)) && r.raw.includes(Buffer.from(marker)));

  check("requests recorded", requests.length > 0, `${requests.length} requests, ${spans.length} spans`);
  check("every request decodes as OTLP protobuf", requests.every((r) => r.meta.decodeError === null));
  check("no request is compressed", requests.every((r) => !r.meta.headers["content-encoding"]));
  check("every request carries X-Api-Key and X-Secret-Key",
    requests.every((r) => /^<set:[1-9]/.test(r.meta.headers["x-api-key"] ?? "") && /^<set:[1-9]/.test(r.meta.headers["x-secret-key"] ?? "")));
  const forwarded = requests.filter((r) => r.meta.forwardStatus !== undefined);
  check("collector accepted every forwarded request", forwarded.every((r) => r.meta.forwardStatus === 200),
    forwarded.filter((r) => r.meta.forwardStatus !== 200).map((r) => `${r.file}:${r.meta.forwardStatus}`).join(" "));
  check("every span has resource project_name", spans.every((s) => typeof s.resource.project_name === "string" && s.resource.project_name));
  const scopes = [...new Set(spans.map((s) => s.scope.name))];
  check("only eve.agent spans exported (workflow dropped)", scopes.length === 1 && scopes[0] === "eve.agent", scopes.join(","));

  const ok = invoke("off.ok");
  const t = trace(ok?.traceId);
  const root = t.find((s) => s.name.startsWith("invoke_agent ") && !s.parentSpanId);
  const steps = t.filter((s) => s.name === "agent.step");
  const chats = t.filter((s) => s.name.startsWith("chat "));
  const tools = t.filter((s) => s.name === "execute_tool get_weather");
  check("off: one trace with invoke_agent root", root && ok.status === "completed", ok?.traceId ?? "no trace id");
  check("off: agent.step children of the root", steps.length >= 2 && steps.every((s) => s.parentSpanId === root?.spanId), `${steps.length} steps`);
  // eve < 0.80 puts an agent.action span between the step and execute_tool.
  const underStep = (s) => {
    const parent = t.find((p) => p.spanId === s.parentSpanId);
    if (parent?.name === "agent.action") return steps.some((p) => p.spanId === parent.parentSpanId);
    return steps.some((p) => p.spanId === s.parentSpanId);
  };
  check("off: chat and execute_tool under a step",
    chats.length >= 2 && tools.length === 1 && [...chats, ...tools].every(underStep));
  check("off: chat spans carry model and token usage",
    chats.every((s) => s.attributes["gen_ai.request.model"] && Number(s.attributes["gen_ai.usage.input_tokens"]) > 0));
  const offIds = [ok?.traceId, invoke("off.toolerr")?.traceId].filter(Boolean);
  check("off: marker absent from every request body", !requests.some((r) => r.raw.includes(Buffer.from(markers.off))), markers.off);
  check("off: no content or principal-id attributes",
    offIds.flatMap(trace).every((s) => CONTENT_KEYS.every((k) => !(k in s.attributes))));

  const te = invoke("off.toolerr");
  const teSpans = trace(te?.traceId);
  const toolErr = teSpans.find((s) => s.name === "execute_tool get_weather");
  check("off: failing tool span has status ERROR", toolErr?.status.code === 2, te?.traceId ?? "no trace id");
  check("off: error text and exception events redacted",
    toolErr && teSpans.every((s) => s.status.message === "" && s.events.every((e) => e.name !== "exception")));
  check("off: last turn exported after SIGINT (shutdown flush)", trace(te?.traceId).some((s) => s.name.startsWith("invoke_agent ")));

  const modelErrSpans = spans.filter((s) => s.name.startsWith("chat ") && s.status.code === 2);
  check("model: failing chat span has status ERROR", modelErrSpans.length > 0, `${modelErrSpans.length} span(s)`);
  check("model: marker absent", !requests.some((r) => r.raw.includes(Buffer.from(markers.model))), markers.model);

  const on = invoke("on.ok");
  const onSpans = trace(on?.traceId);
  check("on: project_name is the opt-in project", onSpans.length > 0 && onSpans.every((s) => s.resource.project_name === `${markers.project}-optin`));
  check("on: marker exported when FI_CAPTURE_CONTENT=1", on && bodyHas(markers.on, [on.traceId]), markers.on);
  check("on: chat span carries gen_ai.input.messages", onSpans.some((s) => s.name.startsWith("chat ") && "gen_ai.input.messages" in s.attributes));
  return results;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const out = process.argv[2] ?? "./evidence";
  const results = checkRun(loadRun(out));
  for (const r of results) console.log(`${r.ok ? "PASS" : "FAIL"} ${r.name}${r.detail ? ` (${r.detail})` : ""}`);
  const failed = results.filter((r) => !r.ok).length;
  console.log(failed ? `\n${failed} check(s) failed` : `\nall ${results.length} checks passed`);
  process.exit(failed ? 1 : 0);
}
