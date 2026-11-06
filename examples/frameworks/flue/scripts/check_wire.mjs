// Checks what run_e2e.sh put on the wire (the recorder's copy of every OTLP
// request) and prints one PASS/FAIL line per check.
//   node scripts/check_wire.mjs <out-dir>
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

/** Span attribute keys that carry prompts, completions, tool payloads or descriptions. */
export const CONTENT_KEYS = [
  "gen_ai.input.messages",
  "gen_ai.output.messages",
  "gen_ai.system_instructions",
  "gen_ai.tool.definitions",
  "gen_ai.tool.description",
  "gen_ai.tool.call.arguments",
  "gen_ai.tool.call.result",
  "flue.tool.call.arguments",
  "flue.tool.call.result",
];

/** Resource attributes the recipe sets. Anything else (host.*, process.*) is a leak. */
export const RESOURCE_KEYS = ["project_name", "project_type", "service.name"];

const readJson = (p) => JSON.parse(readFileSync(p, "utf8").trim().split("\n").pop());

export function loadRun(out) {
  const wireDir = join(out, "wire");
  const files = readdirSync(wireDir).filter((f) => f.endsWith(".json")).sort();
  const requests = files.map((f) => {
    const meta = JSON.parse(readFileSync(join(wireDir, f), "utf8"));
    const raw = readFileSync(join(wireDir, f.replace(/\.json$/, ".bin")));
    return { file: f, meta, raw };
  });
  const markers = readJson(join(out, "markers.json"));
  const identity = readJson(join(out, "identity.json"));
  const envelope = (name) => {
    const p = join(out, `${name}.json`);
    if (!existsSync(p) || readFileSync(p, "utf8").trim() === "") return null;
    return readJson(p);
  };
  const down = existsSync(join(out, "down.exit.json")) ? readJson(join(out, "down.exit.json")) : null;
  return { requests, markers, identity, envelope, down };
}

/** Pure checks over a loaded run. Returns [{ ok, name, detail }]. */
export function checkRun({ requests, markers, identity, envelope, down }, env = process.env) {
  const results = [];
  const check = (name, ok, detail = "") => results.push({ ok: Boolean(ok), name, detail });
  const spans = requests.flatMap((r) => r.meta.spans);
  const bySubmission = (id) => spans.filter((s) => id && s.attributes["flue.submission.id"] === id);
  const has = (s, key) => key in s.attributes;
  const bodyHas = (text) => requests.some((r) => r.raw.includes(Buffer.from(text)));
  const kids = (all, root) => all.filter((s) => s.parentSpanId === root?.spanId);

  check("requests recorded", requests.length > 0, `${requests.length} requests, ${spans.length} spans`);
  check("every request decodes as OTLP protobuf", requests.every((r) => r.meta.decodeError === null));
  check("no request is compressed", requests.every((r) => !r.meta.headers["content-encoding"]));
  check("every request carries X-Api-Key and X-Secret-Key",
    requests.every((r) => /^<set:[1-9]/.test(r.meta.headers["x-api-key"] ?? "") && /^<set:[1-9]/.test(r.meta.headers["x-secret-key"] ?? "")));
  const forwarded = requests.filter((r) => r.meta.forwardStatus !== undefined);
  check("collector accepted every forwarded request", forwarded.length > 0 && forwarded.every((r) => r.meta.forwardStatus === 200),
    forwarded.filter((r) => r.meta.forwardStatus !== 200).map((r) => `${r.file}:${r.meta.forwardStatus}`).join(" "));
  check("every span has resource project_name", spans.every((s) => typeof s.resource.project_name === "string" && s.resource.project_name));
  const extraResource = [...new Set(spans.flatMap((s) => Object.keys(s.resource)).filter((k) => !RESOURCE_KEYS.includes(k)))];
  check("resource carries only project_name, project_type, service.name", extraResource.length === 0, extraResource.join(","));
  const scopes = [...new Set(spans.map((s) => s.scope.name))];
  check("only @flue/opentelemetry spans exported", scopes.length === 1 && scopes[0] === "@flue/opentelemetry", scopes.join(","));

  const leaks = [identity.hostname, identity.user, identity.home, identity.cwd, "/Users/", "/home/"].filter((p) => p && p.length >= 4 && bodyHas(p));
  check("no host name, user name or local path in any request, either mode", leaks.length === 0, leaks.length ? "found a local identity string" : "");
  const secrets = [env.FI_API_KEY, env.FI_SECRET_KEY, env.MODEL_API_KEY, "bad-key"].filter((s) => s && s.length >= 6);
  check("no API key in any request body", !secrets.some((s) => bodyHas(s)));

  // Content off (the default).
  const ok = envelope("off.ok");
  const t = bySubmission(ok?.submissionId);
  const root = t.find((s) => s.name === "invoke_agent Weather" && !s.parentSpanId);
  const chats = t.filter((s) => s.name.startsWith("chat "));
  const tools = t.filter((s) => s.name === "execute_tool get_weather");
  check("off: one trace, invoke_agent root", root && ok.outcome === "completed" && new Set(t.map((s) => s.traceId)).size === 1, ok?.submissionId ?? "no envelope");
  check("off: chat and execute_tool spans are children of the root", chats.length >= 2 && tools.length === 1 && [...chats, ...tools].every((s) => s.parentSpanId === root?.spanId), `${chats.length} chat, ${tools.length} tool`);
  check("off: chat spans carry model, provider and token usage",
    chats.every((s) => s.attributes["gen_ai.request.model"] && s.attributes["gen_ai.provider.name"] && Number(s.attributes["gen_ai.usage.input_tokens"]) > 0 && Number(s.attributes["gen_ai.usage.output_tokens"]) > 0));
  check("off: tool span carries tool name and call id", tools.every((s) => s.attributes["gen_ai.tool.name"] === "get_weather" && s.attributes["gen_ai.tool.call.id"]));
  const offSpans = [ok, envelope("off.toolerr"), envelope("model.err"), envelope("server.ok"), envelope("script.ok")].flatMap((e) => bySubmission(e?.submissionId));
  check("off: marker absent from every request body", ["off", "err", "server", "script"].every((k) => !bodyHas(markers[k])), `${markers.off} ${markers.err} ${markers.server} ${markers.script}`);
  check("off: no content attribute on any span", offSpans.length > 0 && offSpans.every((s) => CONTENT_KEYS.every((k) => !has(s, k))), `${offSpans.length} spans`);

  const te = envelope("off.toolerr");
  const teSpans = bySubmission(te?.submissionId);
  const toolErr = teSpans.find((s) => s.name === "execute_tool get_weather");
  check("off: failing tool span has status ERROR and the error type", toolErr?.status.code === 2 && toolErr.attributes["error.type"], te?.submissionId ?? "no envelope");
  check("off: error text, exception message and stack trace are not exported",
    toolErr && teSpans.every((s) => s.status.message === "" && s.events.every((e) => !("exception.message" in e.attributes) && !("exception.stacktrace" in e.attributes))));

  const me = envelope("model.err");
  const meSpans = bySubmission(me?.submissionId);
  check("model: failing chat span has status ERROR and the run failed", me?.outcome === "failed" && meSpans.some((s) => s.name.startsWith("chat ") && s.status.code === 2 && s.attributes["error.type"]), me?.outcome ?? "no envelope");
  check("model: provider error text is not exported", meSpans.every((s) => s.status.message === "" && s.events.every((e) => !("exception.message" in e.attributes))));

  // Content on (FI_CAPTURE_CONTENT=1).
  const on = envelope("on.ok");
  const onSpans = bySubmission(on?.submissionId);
  check("on: project_name is the opt-in project", onSpans.length > 0 && onSpans.every((s) => s.resource.project_name === markers.optinProject));
  check("on: marker exported in prompt, tool arguments, tool result and answer",
    onSpans.some((s) => String(s.attributes["gen_ai.input.messages"] ?? "").includes(markers.on))
    && onSpans.some((s) => String(s.attributes["gen_ai.tool.call.arguments"] ?? "").includes(markers.on))
    && onSpans.some((s) => String(s.attributes["gen_ai.tool.call.result"] ?? "").includes(markers.on))
    && onSpans.some((s) => String(s.attributes["gen_ai.output.messages"] ?? "").includes(markers.on)), markers.on);
  check("on: system instructions and tool definitions exported", onSpans.some((s) => has(s, "gen_ai.system_instructions") && has(s, "gen_ai.tool.definitions")));
  const oe = envelope("on.toolerr");
  const oeTool = bySubmission(oe?.submissionId).find((s) => s.name === "execute_tool get_weather");
  const oeEvent = oeTool?.events.find((e) => e.name === "exception");
  check("on: exception message exported, stack trace dropped",
    oeTool?.status.code === 2 && String(oeEvent?.attributes["exception.message"] ?? "").includes(markers.on) && !("exception.stacktrace" in (oeEvent?.attributes ?? {})), oe?.submissionId ?? "no envelope");

  // Shutdown paths. OTEL_BSP_SCHEDULE_DELAY is far above the run time, so only a flush on shutdown delivers.
  const srv = envelope("server.ok");
  const srvSpans = bySubmission(srv?.submissionId);
  check("server: spans of the last message arrived after SIGTERM",
    srvSpans.some((s) => s.name === "invoke_agent Weather" && !s.parentSpanId) && srvSpans.some((s) => s.name === "execute_tool get_weather") && srvSpans.filter((s) => s.name.startsWith("chat ")).length >= 2, srv?.submissionId ?? "no envelope");
  const scr = envelope("script.ok");
  const scrSpans = bySubmission(scr?.submissionId);
  check("script: spans arrived when the standalone script's event loop drained",
    scrSpans.some((s) => s.name === "invoke_agent Weather" && !s.parentSpanId) && scrSpans.some((s) => s.name === "execute_tool get_weather"), scr?.submissionId ?? "no envelope");

  // Exporter down.
  const dn = envelope("down.ok");
  check("down: the workflow completed with exit 0 while the exporter could not connect",
    down?.exit === 0 && dn?.outcome === "completed" && String(dn.message).includes(markers.down), down ? `exit ${down.exit}, ${down.elapsedMs} ms` : "no result");
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
