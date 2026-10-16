// Contract test of otelcol.yaml with the real collector image and no Future AGI: the shipped config, with only the
// exporter swapped for a file exporter, transforms the recorded turn plus injected content, identities, log lines and
// errors. Needs Docker (skipped otherwise, or with SKIP_DOCKER=1).
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
  const { spans: rows, logs } = JSON.parse(readFileSync(new URL("./fixtures/local-explorer-happy.json", import.meta.url)));
  const req = rowsToOtlp(rows, logs);
  const spans = req.resourceSpans[0].scopeSpans[0].spans;
  const add = (name, key, value) => spans.filter((s) => s.name.startsWith(name)).forEach((s) => {
    s.attributes = s.attributes.filter((a) => a.key !== key).concat({ key, value: { stringValue: value } });
  });
  // what wrapAISDK writes with storeMessages / storeTools on
  add("chat ", "gen_ai.input.messages", JSON.stringify([{ role: "user", parts: [{ type: "text", content: `weather in ${MARK}` }] }]));
  add("chat ", "gen_ai.output.messages", JSON.stringify([{ role: "assistant", parts: [{ type: "text", content: `sunny in ${MARK}` }] }]));
  add("chat ", "gen_ai.system_instructions", JSON.stringify([{ type: "text", content: `system ${MARK}` }]));
  add("execute_tool", "gen_ai.tool.call.arguments", `{"city":"${MARK}"}`);
  add("execute_tool", "gen_ai.tool.call.result", `{"forecast":"${MARK}"}`);
  add("execute_tool", "error.type", "Error");
  // an Agent instance named after an e-mail address, and a URL with a query string
  add("agent_start", "cloudflare.agents.session.name", `jane.${MARK}@example.com`);
  add("POST", "url.full", `https://agents.example.com/agents/weather-agent/jane.${MARK}%40example.com?token=${MARK}`);
  const tool = spans.find((s) => s.name.startsWith("execute_tool"));
  tool.events = [{ name: "exception", timeUnixNano: tool.startTimeUnixNano, attributes: [
    { key: "exception.type", value: { stringValue: "Error" } },
    { key: "exception.message", value: { stringValue: `no weather station for ${MARK}` } },
    { key: "exception.stacktrace", value: { stringValue: `Error: x\n    at execute (/home/jane/${MARK}/index.ts:12:3)` } },
  ] }];
  tool.status = { code: 2, message: `raw failure text ${MARK}` };
  // console output attributed to a span (encoding not documented by Cloudflare: marker in the name and the attributes)
  const agent = spans.find((s) => s.name.startsWith("invoke_agent"));
  agent.events = [{ name: `console ${MARK}`, timeUnixNano: agent.startTimeUnixNano, attributes: [
    { key: "level", value: { stringValue: "info" } }, { key: "message", value: { stringValue: `user asked about ${MARK} jane@example.com` } },
  ] }];
  return req;
}

async function runCollector(capture) {
  // Under this directory, not the system temp dir: Docker Desktop does not always share the latter.
  const dir = mkdtempSync(join(HERE, ".ctest-"));
  chmodSync(dir, 0o777);
  writeFileSync(join(dir, "override.yaml"), [
    "exporters:", "  file/test:", "    path: /out/spans.json", "service:", "  pipelines:", "    traces:", "      exporters: [file/test]", "",
  ].join("\n"));
  const name = `th8103-rest-cloudflare-agents-ctest-${process.pid}-${capture}`;
  const port = String(14490 + (capture ? 1 : 0));
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
    const noAuth = await fetch(`http://127.0.0.1:${port}/v1/traces`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(fixture()) });
    assert.equal(noAuth.status, 401);
    const res = await fetch(`http://127.0.0.1:${port}/v1/traces`, {
      method: "POST", headers: { "content-type": "application/json", authorization: `Bearer ${TOKEN}` }, body: JSON.stringify(fixture()),
    });
    assert.equal(res.status, 200);
    const out = join(dir, "spans.json");
    for (let i = 0; i < 40 && !(existsSync(out) && readFileSync(out, "utf8").trim()); i++) await new Promise((r) => setTimeout(r, 500));
    const text = readFileSync(out, "utf8");
    return { text, req: JSON.parse(text.trim().split("\n")[0]) };
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
  assert.doesNotMatch(text, /jane@example\.com|127\.0\.0\.1|agents\.example\.com/);
  assert.equal(get({ attributes: req.resourceSpans[0].resource.attributes }, "project_name"), "ctest-project");
  assert.equal(get({ attributes: req.resourceSpans[0].resource.attributes }, "project_type"), "observe");
  const spans = spansOf(req);
  assert.ok(!spans.some((s) => s.name.startsWith("durable_object_storage_")));
  const agent = spans.find((s) => s.name === "invoke_agent weather-agent");
  assert.equal(get(agent, "fi.span.kind"), "AGENT");
  assert.equal(get(agent, "gen_ai.usage.input_tokens"), undefined);
  assert.equal(get(agent, "cloudflare.agents.usage.total_tokens"), "811");
  assert.equal(agent.events, undefined, "console output is dropped");
  const conv = get(agent, "gen_ai.conversation.id");
  assert.equal(get(agent, "session.id"), conv);
  const root = spans.find((s) => !s.parentSpanId);
  assert.equal(get(root, "session.id"), conv, "trace root and Agent spans share the session");
  assert.equal(get(root, "fi.span.kind"), "CHAIN");
  assert.equal(get(root, "url.full"), "/agents/weather-agent/<email>");
  const start = spans.find((s) => s.name === "agent_start");
  assert.equal(get(start, "fi.span.kind"), "CHAIN");
  assert.equal(get(start, "cloudflare.agents.session.name"), "<email>");
  assert.equal(get(start, "session.id"), conv, "lifecycle spans: session from the Durable Object id, the same value");
  const chat = spans.find((s) => s.name.startsWith("chat "));
  assert.equal(get(chat, "gen_ai.input.messages"), undefined);
  assert.equal(get(chat, "gen_ai.system_instructions"), undefined);
  assert.equal(get(chat, "gen_ai.usage.input_tokens"), "365");
  assert.equal(get(chat, "fi.span.kind"), undefined, "Future AGI maps chat itself");
  const tool = spans.find((s) => s.name.startsWith("execute_tool"));
  assert.deepEqual(tool.status, { code: 2, message: "Error" });
  assert.equal(get(tool, "gen_ai.tool.call.arguments"), undefined);
  assert.deepEqual(tool.events[0].attributes, [{ key: "exception.type", value: { stringValue: "Error" } }]);
  const approval = spans.find((s) => s.name.startsWith("tool_approval"));
  assert.equal(get(approval, "fi.span.kind"), "CHAIN");
  assert.equal(get(approval, "cloudflare.agents.tool.approval.state"), "approved");
  const logged = spans.filter((s) => s.events?.some((e) => e.name === "log"));
  assert.deepEqual(logged, [], "runtime log lines are dropped");
});

test("collector, content on (FI_CAPTURE_CONTENT=true)", { skip: !docker && "docker or the collector image is not available" }, async () => {
  const { text, req } = await runCollector(true);
  const spans = spansOf(req);
  const chat = spans.find((s) => s.name.startsWith("chat "));
  assert.match(get(chat, "input.value"), new RegExp(MARK));
  assert.match(get(chat, "output.value"), new RegExp(MARK));
  const tool = spans.find((s) => s.name.startsWith("execute_tool"));
  assert.match(get(tool, "input.value"), new RegExp(MARK));
  assert.match(get(tool, "output.value"), new RegExp(MARK));
  assert.equal(tool.status.message, "Error", "status keeps the error class");
  assert.equal(tool.events[0].attributes.length, 3, "exception details pass through when you opt in");
  const agent = spans.find((s) => s.name === "invoke_agent weather-agent");
  assert.equal(agent.events.length, 1, "console output passes through when you opt in");
  assert.match(get(agent.events[0], "message"), /<email>/, "e-mail-shaped values are replaced on span events in both modes");
  const start = spans.find((s) => s.name === "agent_start");
  assert.equal(get(start, "cloudflare.agents.session.name"), "<email>", "e-mail-shaped values are replaced in both modes");
  assert.doesNotMatch(text, /jane@example\.com|jane\.[a-z0-9]+(@|%40)example\.com/);
});
