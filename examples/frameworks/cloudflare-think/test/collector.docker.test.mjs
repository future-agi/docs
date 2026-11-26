// The real OpenTelemetry Collector running otelcol.yaml, fed a real Workers destination export recorded on
// 2026-10-18 (test/fixtures/cloudflare-export-2026-10-18.json: the bodies Cloudflare posted, sanitized, marker
// text replaced). Each body is sent the way the destination sends it: OTLP/HTTP JSON, gzip, bearer header.
// The Future AGI exporter is swapped for a file exporter by an overlay config, so nothing leaves the machine.
// Needs Docker; skipped without it.
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const IMAGE = "otel/opentelemetry-collector-contrib:0.162.0";
const CONFIG = fileURLToPath(new URL("../otelcol.yaml", import.meta.url));
const BODIES = JSON.parse(readFileSync(new URL("./fixtures/cloudflare-export-2026-10-18.json", import.meta.url), "utf8"));
const MARKER = "MARKER-FIXTURE";
const TOKEN = "test-collector-token";
const hasDocker = spawnSync("docker", ["info"], { stdio: "ignore" }).status === 0;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const val = (v) => (v ? Object.values(v)[0] : undefined);
const attrs = (list) => Object.fromEntries((list || []).map((a) => [a.key, val(a.value)]));

async function post(port, body, headers = {}) {
  const res = await fetch(`http://127.0.0.1:${port}/v1/traces`, {
    method: "POST",
    headers: { "content-type": "application/json", "content-encoding": "gzip", authorization: `Bearer ${TOKEN}`, ...headers },
    body: gzipSync(JSON.stringify(body)),
  });
  await res.arrayBuffer();
  return res.status;
}

// Runs the collector, posts every recorded body, returns the spans it would have sent to Future AGI.
async function collect(content) {
  // Under the example's git-ignored evidence/ directory, not the system temp dir: Docker on macOS often shares
  // only the home directory with its VM, so a bind mount from /tmp or /var/folders arrives empty.
  const base = fileURLToPath(new URL("../evidence/", import.meta.url));
  mkdirSync(base, { recursive: true });
  const dir = mkdtempSync(join(base, "otelcol-test-"));
  chmodSync(dir, 0o777);
  writeFileSync(join(dir, "overlay.yaml"), [
    "exporters:",
    "  file/test:",
    "    path: /out/spans.json",
    "    format: json",
    "    flush_interval: 100ms",
    "service:",
    "  pipelines:",
    "    traces:",
    "      exporters: [file/test]",
    "",
  ].join("\n"));
  const name = `cfthink-otelcol-test-${process.pid}-${content ? "on" : "off"}`;
  const env = ["COLLECTOR_TOKEN=" + TOKEN, "FI_API_KEY=unused", "FI_SECRET_KEY=unused", "FI_PROJECT_NAME=think-weather-test",
    "FI_TRACES_URL=http://127.0.0.1:9/v1/traces", ...(content ? ["FI_CAPTURE_CONTENT=true"] : [])];
  execFileSync("docker", ["run", "-d", "--name", name, "--memory", "256m", "-p", "127.0.0.1::4318",
    "-v", `${CONFIG}:/etc/otelcol-contrib/config.yaml:ro`, "-v", `${dir}:/out`,
    ...env.flatMap((e) => ["-e", e]), IMAGE, "--config=/etc/otelcol-contrib/config.yaml", "--config=/out/overlay.yaml"]);
  try {
    const port = execFileSync("docker", ["port", name, "4318/tcp"], { encoding: "utf8" }).trim().split(":").pop();
    let ready = false;
    for (let i = 0; i < 60 && !ready; i++) {
      try { ready = (await post(port, { resourceSpans: [] })) === 200; } catch { await sleep(250); }
    }
    assert.ok(ready, "collector came up");
    assert.equal(await post(port, BODIES[0], { authorization: "Bearer wrong" }), 401, "a wrong bearer is rejected");
    for (const body of BODIES) assert.equal(await post(port, body), 200);
    const file = join(dir, "spans.json");
    let spans = [];
    for (let i = 0; i < 60; i++) {
      await sleep(250);
      if (!existsSync(file)) continue;
      const lines = readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
      spans = lines.flatMap((b) => b.resourceSpans.flatMap((rs) =>
        rs.scopeSpans.flatMap((ss) => ss.spans.map((s) => ({ ...s, resource: attrs(rs.resource.attributes), attrs: attrs(s.attributes) })))));
      if (i > 12 && spans.length) break;
    }
    return { spans, raw: existsSync(file) ? readFileSync(file, "utf8") : "" };
  } finally {
    spawnSync("docker", ["rm", "-f", name], { stdio: "ignore" });
    rmSync(dir, { recursive: true, force: true });
  }
}

const inFixture = BODIES.flatMap((b) => b.resourceSpans.flatMap((rs) => rs.scopeSpans.flatMap((ss) => ss.spans)));
const opOf = (s) => s.attrs["gen_ai.operation.name"];

test("fixture is a real export: pre-flight body, storage spans, payloads, url.query with the marker", () => {
  const sdk = BODIES.flatMap((b) => b.resourceSpans.map((rs) => attrs(rs.resource.attributes)["telemetry.sdk.name"]));
  assert.ok(sdk.includes("pre-flight-check") && sdk.includes("workers-observability"));
  assert.ok(inFixture.some((s) => s.name.startsWith("durable_object_storage_")));
  const raw = JSON.stringify(BODIES);
  for (const k of ["gen_ai.input.messages", "gen_ai.tool.call.arguments", "url.query", "gen_ai.usage.input_tokens"]) assert.ok(raw.includes(k), k);
  assert.ok(raw.includes(MARKER));
});

test("content off (default): what reaches Future AGI", { skip: !hasDocker && "needs Docker" }, async () => {
  const { spans, raw } = await collect(false);
  assert.ok(spans.length > 0);
  assert.ok(!raw.includes(MARKER), "the marker (prompt, tool argument and result, query string) is not forwarded");
  assert.ok(!spans.some((s) => s.name.startsWith("Hello from Cloudflare")), "pre-flight test span dropped");
  assert.ok(!spans.some((s) => s.name.startsWith("durable_object_storage_")), "storage spans dropped");
  for (const s of spans) {
    assert.equal(s.resource.project_name, "think-weather-test");
    assert.equal(s.attrs["url.query"], undefined, `url.query on ${s.name}`);
    if (s.attrs["url.full"]) assert.doesNotMatch(s.attrs["url.full"], /[?#]/);
    for (const k of Object.keys(s.attrs)) assert.doesNotMatch(k, /^gen_ai\.(input|output)\.messages|^gen_ai\.tool\.call\.(arguments|result)|^gen_ai\.system_instructions/);
  }
  const agent = spans.filter((s) => opOf(s) === "invoke_agent");
  const chats = spans.filter((s) => opOf(s) === "chat");
  const tools = spans.filter((s) => opOf(s) === "execute_tool");
  assert.ok(agent.length && chats.length && tools.length);
  for (const a of agent) {
    assert.equal(a.attrs["fi.span.kind"], "AGENT");
    assert.ok(!Object.keys(a.attrs).some((k) => k.startsWith("gen_ai.usage.")), "turn totals are not counted a second time");
    if (a.attrs["think.turn.input_tokens"] !== undefined) assert.ok(Number(a.attrs["think.turn.input_tokens"]) > 0);
    assert.equal(a.attrs["session.id"], a.attrs["gen_ai.conversation.id"]);
  }
  // Each completed turn's totals equal the sum of its chat spans, which keep their own usage.
  for (const a of agent.filter((x) => x.attrs["think.turn.input_tokens"] !== undefined)) {
    const kids = chats.filter((c) => c.parentSpanId === a.spanId);
    assert.equal(kids.reduce((n, c) => n + Number(c.attrs["gen_ai.usage.input_tokens"]), 0), Number(a.attrs["think.turn.input_tokens"]));
  }
  for (const c of chats) assert.equal(c.attrs["fi.span.kind"], "LLM");
  for (const t of tools) assert.equal(t.attrs["fi.span.kind"], "TOOL");
  for (const s of spans.filter((x) => x.attrs["error.type"] !== undefined)) assert.equal(s.status?.code, 2, `${s.name} is ERROR`);
  assert.ok(spans.some((s) => s.attrs["error.type"] !== undefined), "the fixture has a failed tool or model call");
  for (const s of spans) for (const e of s.events || []) assert.equal(e.name, "exception");
});

test("content on (FI_CAPTURE_CONTENT=true): payloads fill Input and Output", { skip: !hasDocker && "needs Docker" }, async () => {
  const { spans, raw } = await collect(true);
  assert.ok(raw.includes(MARKER), "payloads are forwarded");
  const withPayload = spans.filter((s) => s.attrs["gen_ai.input.messages"] !== undefined || s.attrs["gen_ai.tool.call.arguments"] !== undefined);
  assert.ok(withPayload.length > 0);
  for (const s of withPayload) {
    assert.ok(String(s.attrs["input.value"]).length > 0, `input.value on ${s.name}`);
    assert.ok(String(s.attrs["output.value"] ?? "").length > 0 || opOf(s) === "chat", `output.value on ${s.name}`);
  }
  // Query strings are cut with content on too.
  assert.ok(!spans.some((s) => s.attrs["url.query"] !== undefined));
});
