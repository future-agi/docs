// Static checks on what the page tells you to deploy: otelcol.yaml, wrangler.jsonc, src/index.ts, and that the
// page shows the same executable configuration and Worker code.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { parse } from "yaml";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const cfgText = read("otelcol.yaml");
const cfg = parse(cfgText);
const PAGE = new URL("../../../../src/pages/docs/integrations/frameworks/cloudflare-agents.mdx", import.meta.url);
const OFF = '"${env:FI_CAPTURE_CONTENT:-false}" != "true"';

test("collector: traces only, no self-metrics, uncompressed export with both Future AGI key headers", () => {
  assert.equal(cfg.service.telemetry.metrics.level, "none");
  assert.deepEqual(Object.keys(cfg.service.pipelines), ["traces"]);
  const exp = cfg.exporters["otlp_http/future_agi"];
  assert.equal(exp.compression, "none");
  assert.equal(exp.headers["X-Api-Key"], "${env:FI_API_KEY}");
  assert.equal(exp.headers["X-Secret-Key"], "${env:FI_SECRET_KEY}");
  assert.equal(exp.traces_endpoint, "${env:FI_TRACES_URL}");
});

test("collector: the receiver requires the destination's bearer token", () => {
  assert.equal(cfg.receivers.otlp.protocols.http.auth.authenticator, "bearertokenauth/cloudflare");
  assert.equal(cfg.extensions["bearertokenauth/cloudflare"].token, "${env:CF_DESTINATION_TOKEN}");
  assert.ok(!cfg.receivers.otlp.protocols.grpc, "no gRPC receiver: Cloudflare sends OTLP/HTTP");
  assert.deepEqual(cfg.service.extensions, ["bearertokenauth/cloudflare"]);
});

test("collector: stamps project_name as a resource attribute, drops storage spans, maps types and sessions", () => {
  const res = cfg.processors["resource/future_agi"].attributes;
  assert.deepEqual(res.find((a) => a.key === "project_name"), { key: "project_name", value: "${env:FI_PROJECT_NAME}", action: "upsert" });
  assert.deepEqual(cfg.processors["filter/storage_spans"].traces.span, ['IsMatch(name, "^durable_object_storage_")']);
  const st = cfg.processors["transform/cloudflare_agents"].trace_statements[0].statements;
  const has = (s) => assert.ok(st.includes(s), `missing statement: ${s}`);
  has('set(attributes["fi.span.kind"], "AGENT") where attributes["gen_ai.operation.name"] == "invoke_agent"');
  has('set(attributes["fi.span.kind"], "CHAIN") where attributes["cloudflare.agents.operation.name"] == "tool.approval"');
  has('set(attributes["fi.span.kind"], "CHAIN") where attributes["gen_ai.operation.name"] == nil');
  has('delete_matching_keys(attributes, "^gen_ai\\\\.usage\\\\.") where attributes["gen_ai.operation.name"] == "invoke_agent"');
  has('set(attributes["session.id"], attributes["gen_ai.conversation.id"]) where attributes["gen_ai.conversation.id"] != nil');
  has('set(status.code, STATUS_CODE_ERROR) where attributes["error.type"] != nil');
  // the conversation id wins over the Durable Object id when both are present: it is set last
  assert.ok(st.findIndex((s) => s.includes('"cloudflare.agents.session.id"]) where')) < st.findIndex((s) => s.includes('"gen_ai.conversation.id"]) where')));
  assert.deepEqual(cfg.service.pipelines.traces.processors,
    ["filter/preflight", "filter/storage_spans", "resource/future_agi", "transform/cloudflare_agents", "filter/span_events", "batch"]);
});

test("collector: the destination's pre-flight test span is not forwarded (seen in the real export)", () => {
  assert.deepEqual(cfg.processors["filter/preflight"].traces.span, ['resource.attributes["telemetry.sdk.name"] == "pre-flight-check"']);
});

test("collector: content is off unless FI_CAPTURE_CONTENT=true", () => {
  const ts = cfg.processors["transform/cloudflare_agents"].trace_statements;
  const span = ts[0].statements;
  for (const s of span.filter((s) => s.startsWith('set(attributes["input.value"]') || s.startsWith('set(attributes["output.value"]'))) {
    assert.ok(s.endsWith('"${env:FI_CAPTURE_CONTENT:-false}" == "true"'), s);
  }
  const del = span.find((s) => s.includes("input\\\\.messages"));
  for (const k of ["output\\\\.messages", "system_instructions", "tool\\\\.call\\\\.arguments", "tool\\\\.call\\\\.result"]) assert.ok(del.includes(k), k);
  assert.ok(del.endsWith(OFF));
  assert.ok(span.includes(`set(status.message, "error") where status.message != "" and ${OFF}`));
  assert.equal(ts[1].context, "spanevent");
  assert.equal(ts[1].statements[0], `keep_keys(attributes, ["exception.type"]) where ${OFF}`);
  assert.deepEqual(cfg.processors["filter/span_events"].traces.spanevent, [`name != "exception" and ${OFF}`]);
});

test("collector: URLs keep the path only; e-mail-shaped values are replaced on spans and span events in both modes", () => {
  const ts = cfg.processors["transform/cloudflare_agents"].trace_statements;
  assert.ok(ts[0].statements.some((s) => s.startsWith('replace_pattern(attributes["url.full"]') && !s.includes("FI_CAPTURE_CONTENT")));
  // Cloudflare also sends the query string on its own (url.query): dropped in both modes
  assert.ok(ts[0].statements.includes('delete_key(attributes, "url.query")'));
  for (const ctx of ts) {
    const r = ctx.statements.find((s) => s.startsWith("replace_all_patterns(attributes"));
    assert.ok(r && r.includes("(@|%40)") && !r.includes("FI_CAPTURE_CONTENT"), ctx.context);
  }
});

test("collector: the caller's location and network (Cloudflare request spans) are out unless FI_CAPTURE_CONTENT=true", () => {
  const st = cfg.processors["transform/cloudflare_agents"].trace_statements[0].statements;
  assert.ok(st.includes(`delete_matching_keys(attributes, "^geo\\\\.") where ${OFF}`));
  assert.ok(st.includes(`delete_key(attributes, "cloudflare.asn") where ${OFF}`));
});

test("collector: no secret literals", () => {
  assert.doesNotMatch(cfgText, /(sk-[A-Za-z0-9]|Bearer [A-Za-z0-9])/);
});

test("wrangler.jsonc: tracing on, one named destination, no copy in Cloudflare, nodejs_compat, no key literal", () => {
  const text = read("wrangler.jsonc");
  const json = JSON.parse(text.replace(/^\s*\/\/.*$/gm, "").replace(/\s+\/\/ .*$/gm, ""));
  assert.equal(json.observability.traces.enabled, true);
  assert.deepEqual(json.observability.traces.destinations, ["future-agi"]);
  assert.equal(json.observability.traces.persist, false);
  assert.ok(json.compatibility_flags.includes("nodejs_compat"));
  assert.deepEqual(json.durable_objects.bindings, [{ name: "WeatherAgent", class_name: "WeatherAgent" }]);
  assert.deepEqual(json.migrations[0].new_sqlite_classes, ["WeatherAgent"]);
  assert.equal(json.vars, undefined, "no vars block: secrets go through `wrangler secret put`");
  assert.doesNotMatch(text, /OPENAI_API_KEY"\s*:/);
});

test("Worker: a plain Agent that traces the AI SDK with payloads off by default, one tool, identity, root session", () => {
  const src = read("src/index.ts");
  assert.match(src, /class WeatherAgent extends Agent<Env>/);
  assert.match(src, /import \{ Agent, routeAgentRequest \} from "agents"/);
  assert.match(src, /import \{ wrapAISDK \} from "agents\/observability\/ai"/);
  assert.doesNotMatch(src, /@cloudflare\/(think|ai-chat)/, "this page is the plain Agent, not Think or AI Chat");
  assert.match(src, /storeMessages: this\.env\.STORE_MESSAGES === "true"/);
  assert.match(src, /storeTools: this\.env\.STORE_TOOLS === "true"/);
  assert.match(src, /get_weather: ai\.tool\(/);
  assert.match(src, /runtimeContext: \{ agentId: this\.name, conversationId: this\.ctx\.id\.toString\(\) \}/);
  assert.match(src, /functionId: "weather-agent"/);
  assert.match(src, /tracing\.getActiveSpan\(\)\?\.setAttribute\("gen_ai\.conversation\.id", env\.WeatherAgent\.idFromName\(name\)\.toString\(\)\)/);
  assert.doesNotMatch(src, /futureagi|X-Api-Key|FI_API_KEY/i, "the Worker never holds Future AGI keys");
  assert.doesNotMatch(src, /env\.AI\b|workers-ai/i, "no Workers AI provider (different page)");
  const pkg = JSON.parse(read("package.json"));
  assert.equal(pkg.dependencies.agents, "0.28.1");
  assert.equal(pkg.dependencies["@cloudflare/think"], undefined);
  assert.equal(pkg.dependencies["@cloudflare/ai-chat"], undefined);
});

test("page shows the shipped configuration and Worker", { skip: !existsSync(PAGE) && "page not in this checkout" }, () => {
  const page = readFileSync(PAGE, "utf8");
  for (const f of ["otelcol.yaml", "wrangler.jsonc", "src/index.ts"]) {
    const fence = new RegExp('```[^\\n]+ title="' + f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + '"\\n([\\s\\S]*?)```');
    const shown = page.match(fence)?.[1];
    assert.ok(shown, `${f} is missing from the page`);
    // Documentation comments can differ; compare every executable line unchanged.
    const code = (text) => text.split("\n").filter((line) => !/^\s*(?:\/\/|#)/.test(line) && line.trim()).join("\n").trim();
    assert.equal(code(shown), code(read(f)), `${f} differs from the page`);
  }
});

test("page provides a customer setup without a verification diary", { skip: !existsSync(PAGE) && "page not in this checkout" }, () => {
  const page = readFileSync(PAGE, "utf8");
  assert.match(page, /Workers Paid/);
  assert.match(page, /public HTTPS endpoint protected by the bearer token/);
  assert.match(page, /awaited HTTP `generateText`/);
  assert.match(page, /\/agents\/weather-agent\/demo/);
  assert.match(page, /FI_CAPTURE_CONTENT/);
  assert.match(page, /both are off by default/);
  assert.doesNotMatch(page, /live vendor verification|what the live run showed|how this was checked|run_e2e\.sh/i);
});
