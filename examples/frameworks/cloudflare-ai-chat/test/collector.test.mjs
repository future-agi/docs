// Contract test of otelcol.yaml with the real collector image and no Future AGI: the shipped config, with only the
// exporter swapped for a file exporter, transforms
//   - the local workerd fixture turn plus injected content, identities and errors, and
//   - a sanitized export from a REAL Cloudflare Workers traces destination (2026-10-18, deployed Worker): the
//     destination's pre-flight span, a WebSocket upgrade, a tool-error turn, a model-error turn, a content-on turn.
// Needs Docker (skipped otherwise, or with SKIP_DOCKER=1).
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, rmSync, chmodSync } from "node:fs";
import { join } from "node:path";
import { rowsToOtlp } from "../standin/destination.mjs";

const IMAGE = `otel/opentelemetry-collector-contrib:${process.env.OTELCOL_VERSION || "0.162.0"}`;
const docker = !process.env.SKIP_DOCKER && spawnSync("docker", ["image", "inspect", IMAGE], { stdio: "ignore" }).status === 0;
const HERE = new URL("..", import.meta.url).pathname;
const MARK = "ctmark" + Math.random().toString(16).slice(2, 10);
const TOKEN = "cfd-test-" + Math.random().toString(16).slice(2);

function fixture() {
  const rows = JSON.parse(readFileSync(new URL("./fixtures/local-explorer-rows.json", import.meta.url)));
  const req = rowsToOtlp(rows);
  const spans = req.resourceSpans[0].scopeSpans[0].spans;
  const add = (name, key, value) => spans.filter((s) => s.name.startsWith(name)).forEach((s) => {
    s.attributes = s.attributes.filter((a) => a.key !== key).concat({ key, value: { stringValue: value } });
  });
  add("chat ", "gen_ai.input.messages", JSON.stringify([{ role: "user", parts: [{ type: "text", content: `order ${MARK}` }] }]));
  add("chat ", "gen_ai.output.messages", JSON.stringify([{ role: "assistant", parts: [{ type: "text", content: `shipped ${MARK}` }] }]));
  add("execute_tool", "gen_ai.tool.call.arguments", `{"orderId":"${MARK}"}`);
  add("execute_tool", "gen_ai.tool.call.result", `{"status":"${MARK}"}`);
  add("execute_tool", "error.type", "Error");
  add("chat_turn", "cloudflare.agents.session.name", `jane.${MARK}@example.com`);
  add("GET", "url.full", `https://chat.example.com/agents/support-chat/jane.${MARK}%40example.com?token=${MARK}`);
  const tool = spans.find((s) => s.name.startsWith("execute_tool"));
  tool.events = [{ name: "exception", timeUnixNano: tool.startTimeUnixNano, attributes: [
    { key: "exception.type", value: { stringValue: "Error" } },
    { key: "exception.message", value: { stringValue: `backend down for ${MARK}` } },
    { key: "exception.stacktrace", value: { stringValue: `Error: x\n    at lookup (/home/jane/${MARK}/index.ts:12:3)` } },
  ] }];
  tool.status = { code: 2, message: `raw failure text ${MARK}` };
  return req;
}

function realExport() {
  return JSON.parse(readFileSync(new URL("./fixtures/cloudflare-export-2026-10-18.json", import.meta.url)));
}

async function runCollector(capture, body = fixture()) {
  // Under this directory, not the system temp dir: Docker Desktop does not always share the latter.
  const dir = mkdtempSync(join(HERE, ".ctest-"));
  chmodSync(dir, 0o777);
  writeFileSync(join(dir, "override.yaml"), [
    "exporters:", "  file/test:", "    path: /out/spans.json", "service:", "  pipelines:", "    traces:", "      exporters: [file/test]", "",
  ].join("\n"));
  const name = `th8103-rest-cloudflare-ai-chat-ctest-${process.pid}-${capture}`;
  const port = String(14470 + (capture ? 1 : 0));
  execFileSync("docker", ["run", "-d", "--name", name, "--memory", "256m", "-p", `127.0.0.1:${port}:4318`,
    "-e", `CF_DESTINATION_TOKEN=${TOKEN}`, "-e", "FI_API_KEY=unused", "-e", "FI_SECRET_KEY=unused",
    "-e", "FI_TRACES_URL=http://127.0.0.1:9/v1/traces", "-e", "FI_PROJECT_NAME=ctest-project", "-e", `FI_CAPTURE_CONTENT=${capture}`,
    "-v", `${HERE}otelcol.yaml:/etc/otelcol-contrib/config.yaml:ro`, "-v", `${dir}:/out`,
    IMAGE, "--config", "/etc/otelcol-contrib/config.yaml", "--config", "/out/override.yaml"], { stdio: "ignore" });
  try {
    let ready = false;
    for (let i = 0; i < 40 && !ready; i++) {
      try { ready = (await fetch(`http://127.0.0.1:${port}/v1/traces`, { method: "POST", body: "{}" })).status === 401; } catch {}
      if (!ready) await new Promise((r) => setTimeout(r, 500));
    }
    assert.ok(ready, "collector did not start");
    const noAuth = await fetch(`http://127.0.0.1:${port}/v1/traces`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    assert.equal(noAuth.status, 401);
    const res = await fetch(`http://127.0.0.1:${port}/v1/traces`, {
      method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(body),
    });
    assert.equal(res.status, 200);
    const out = join(dir, "spans.json");
    for (let i = 0; i < 40 && !(existsSync(out) && readFileSync(out, "utf8").trim()); i++) await new Promise((r) => setTimeout(r, 500));
    await new Promise((r) => setTimeout(r, 3000)); // the batch processor may flush a large request in more than one write
    const text = readFileSync(out, "utf8");
    const lines = text.trim().split("\n").map((l) => JSON.parse(l));
    return { text, req: lines[0], all: { resourceSpans: lines.flatMap((l) => l.resourceSpans) } };
  } finally {
    spawnSync("docker", ["rm", "-f", name], { stdio: "ignore" });
    rmSync(dir, { recursive: true, force: true });
  }
}

const spansOf = (req) => req.resourceSpans.flatMap((rs) => rs.scopeSpans.flatMap((ss) => ss.spans));
const get = (s, k) => { const v = s.attributes?.find((a) => a.key === k)?.value; return v && (v.stringValue ?? v.intValue ?? v.boolValue); };

test("collector, content off (default)", { skip: !docker && "docker or the collector image is not available" }, async () => {
  const { text, req } = await runCollector(false);
  const leaks = text.split(/[{}]/).filter((p) => p.includes(MARK)).map((p) => p.slice(0, 160));
  assert.deepEqual(leaks, [], "marker reached the exporter");
  assert.equal(get({ attributes: req.resourceSpans[0].resource.attributes }, "project_name"), "ctest-project");
  const spans = spansOf(req);
  assert.ok(!spans.some((s) => s.name.startsWith("durable_object_storage_")));
  const agent = spans.find((s) => s.name === "invoke_agent support-chat");
  assert.equal(get(agent, "gen_ai.span.kind"), "AGENT");
  assert.equal(get(agent, "gen_ai.usage.input_tokens"), undefined);
  assert.equal(get(agent, "cloudflare.agents.usage.total_tokens"), "829");
  assert.ok(get(agent, "session.id"));
  const turn = spans.find((s) => s.name === "chat_turn");
  assert.equal(get(turn, "fi.span.kind"), "CHAIN");
  assert.equal(get(turn, "cloudflare.agents.session.name"), "<email>");
  const chat = spans.find((s) => s.name.startsWith("chat "));
  assert.equal(get(chat, "gen_ai.input.messages"), undefined);
  assert.equal(get(chat, "gen_ai.usage.input_tokens"), "371");
  const tool = spans.find((s) => s.name.startsWith("execute_tool"));
  assert.deepEqual(tool.status, { code: 2, message: "Error" });
  assert.equal(get(tool, "gen_ai.tool.call.arguments"), undefined);
  assert.deepEqual(tool.events[0].attributes, [{ key: "exception.type", value: { stringValue: "Error" } }]);
  const root = spans.find((s) => s.name === "GET" && !s.parentSpanId);
  assert.equal(get(root, "url.full"), "/agents/support-chat/<email>");
});

test("collector, content on (FI_CAPTURE_CONTENT=true)", { skip: !docker && "docker or the collector image is not available" }, async () => {
  const { req } = await runCollector(true);
  const spans = spansOf(req);
  const chat = spans.find((s) => s.name.startsWith("chat "));
  assert.match(get(chat, "input.value"), new RegExp(MARK));
  assert.match(get(chat, "output.value"), new RegExp(MARK));
  const tool = spans.find((s) => s.name.startsWith("execute_tool"));
  assert.match(get(tool, "input.value"), new RegExp(MARK));
  assert.match(get(tool, "output.value"), new RegExp(MARK));
  assert.match(tool.status.message, /Error/);
  assert.equal(tool.events[0].attributes.length, 3, "exception details pass through when you opt in");
  const turn = spans.find((s) => s.name === "chat_turn");
  assert.equal(get(turn, "cloudflare.agents.session.name"), "<email>", "e-mail-shaped values are replaced in both modes");
});

// --- Real Cloudflare export (sanitized: names, e-mail, markers, geo and ASN replaced; at most 2 storage spans a trace) ---
const RT = {
  preflight: "60a1c4c7dc4d749db7954df84ab40e56", upgrade: "460bb59016fb701f01d5d948b79f814a",
  toolError: "0513e9702f14429526374a9575c6f5c9", modelError: "91f38f5af1290a075cf29b40b79c1d92",
  contentOn: "4e4127af764b4ba99a896ad1ec48cf05", close: "f5a18e0a3b4d5fda8d8d3393df002dde",
};
const inTrace = (spans, t) => spans.filter((s) => s.traceId === t);

test("real Cloudflare export: raw shape the collector relies on", () => {
  const spans = spansOf(realExport());
  // One ResourceSpans per span, the destination's own resource, no project_name.
  const res = realExport().resourceSpans.map((rs) => get({ attributes: rs.resource.attributes }, "telemetry.sdk.name"));
  assert.ok(res.includes("workers-observability") && res.includes("pre-flight-check"));
  assert.ok(!realExport().resourceSpans.some((rs) => get({ attributes: rs.resource.attributes }, "project_name")));
  // The turn is its own trace, rooted at the hibernatableWebSocket invocation, not under the upgrade GET.
  const turnRoot = inTrace(spans, RT.toolError).find((s) => !s.parentSpanId);
  assert.equal(turnRoot.name, "hibernatableWebSocket");
  // Failures: error.type only, span status left UNSET by the Agents SDK.
  const tool = inTrace(spans, RT.toolError).find((s) => s.name === "execute_tool lookup_order");
  assert.equal(get(tool, "error.type"), "Error");
  assert.equal(tool.status.code ?? 0, 0);
  // invoke_agent repeats the usage of its chat spans.
  const agent = inTrace(spans, RT.toolError).find((s) => s.name === "invoke_agent support-chat");
  const chats = inTrace(spans, RT.toolError).filter((s) => s.name === "chat gpt-4o-mini");
  assert.equal(Number(get(agent, "gen_ai.usage.input_tokens")), chats.reduce((n, c) => n + Number(get(c, "gen_ai.usage.input_tokens")), 0));
});

test("collector, real Cloudflare export, content off (default)", { skip: !docker && "docker or the collector image is not available" }, async () => {
  const { text, all } = await runCollector(false, realExport());
  for (const needle of ["fixmarkon", "jane.doe", "Example City", "Example Region"]) {
    assert.ok(!text.includes(needle), `${needle} reached the exporter`);
  }
  const spans = spansOf(all);
  assert.ok(all.resourceSpans.every((rs) => get({ attributes: rs.resource.attributes }, "project_name") === "ctest-project"));
  assert.equal(inTrace(spans, RT.preflight).length, 0, "the destination's pre-flight span is dropped");
  assert.ok(!spans.some((s) => s.name.startsWith("durable_object_storage_")));
  // The upgrade GET ends with responseStreamDisconnected when the client closes the socket: not an error.
  const upgrade = inTrace(spans, RT.upgrade).find((s) => s.name === "GET" && !s.parentSpanId);
  assert.equal(upgrade.status.code ?? 0, 0);
  assert.equal(get(upgrade, "cloudflare.outcome"), "responseStreamDisconnected");
  assert.equal(get(upgrade, "url.full"), "/agents/support-chat/<email>");
  assert.equal(get(upgrade, "url.path"), "/agents/support-chat/<email>");
  assert.equal(get(upgrade, "url.query"), undefined);
  assert.equal(get(upgrade, "geo.locality.name"), undefined);
  assert.equal(get(upgrade, "geo.locality.region"), undefined);
  assert.equal(get(upgrade, "geo.country.code"), "US");
  // Tool error turn.
  const tool = inTrace(spans, RT.toolError).find((s) => s.name === "execute_tool lookup_order");
  assert.deepEqual(tool.status, { code: 2, message: "Error" });
  const agent = inTrace(spans, RT.toolError).find((s) => s.name === "invoke_agent support-chat");
  assert.equal(get(agent, "gen_ai.span.kind"), "AGENT");
  assert.equal(get(agent, "gen_ai.usage.input_tokens"), undefined);
  assert.ok(get(agent, "cloudflare.agents.usage.total_tokens"));
  assert.equal(get(agent, "gen_ai.agent.id"), "<email>");
  assert.ok(get(agent, "session.id"));
  const chat = inTrace(spans, RT.toolError).find((s) => s.name === "chat gpt-4o-mini");
  assert.ok(Number(get(chat, "gen_ai.usage.input_tokens")) > 0);
  assert.equal(get(chat, "gen_ai.response.model"), "gpt-4o-mini-2024-07-18");
  // Model error turn: chat and invoke_agent ERROR with the class name; the provider fetch is ERROR (HTTP 404).
  const errs = inTrace(spans, RT.modelError).filter((s) => s.status.code === 2).map((s) => [s.name, s.status.message ?? ""]).sort();
  assert.deepEqual(errs, [["chat no-such-model-th8260", "AI_APICallError"], ["fetch", ""], ["invoke_agent support-chat", "AI_APICallError"]]);
  // Content-on Worker, collector default: the messages and tool payloads Cloudflare recorded are removed.
  const onChat = inTrace(spans, RT.contentOn).find((s) => s.name === "chat gpt-4o-mini");
  assert.equal(get(onChat, "gen_ai.input.messages"), undefined);
  assert.equal(get(onChat, "input.value"), undefined);
  const onTool = inTrace(spans, RT.contentOn).find((s) => s.name === "execute_tool lookup_order");
  assert.equal(get(onTool, "gen_ai.tool.call.arguments"), undefined);
  assert.equal(inTrace(spans, RT.close).length, 1);
});

test("collector, real Cloudflare export, content on (FI_CAPTURE_CONTENT=true)", { skip: !docker && "docker or the collector image is not available" }, async () => {
  const { text, all } = await runCollector(true, realExport());
  for (const needle of ["jane.doe", "Example City", "Example Region"]) {
    assert.ok(!text.includes(needle), `${needle} reached the exporter`);
  }
  const spans = spansOf(all);
  const chats = inTrace(spans, RT.contentOn).filter((s) => s.name === "chat gpt-4o-mini");
  assert.ok(chats.every((c) => /fixmarkon/.test(get(c, "output.value"))));
  assert.ok(chats.every((c) => /support agent/.test(get(c, "input.value"))));
  const tool = inTrace(spans, RT.contentOn).find((s) => s.name === "execute_tool lookup_order");
  assert.match(get(tool, "input.value"), /fixmarkon/);
  assert.match(get(tool, "output.value"), /shipped/);
  assert.equal(inTrace(spans, RT.preflight).length, 0);
});
