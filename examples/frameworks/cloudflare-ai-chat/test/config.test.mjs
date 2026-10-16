// Static checks on what the page tells you to deploy: otelcol.yaml, wrangler.jsonc, src/index.ts, and that the
// page shows those files verbatim.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { parse } from "yaml";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const cfgText = read("otelcol.yaml");
const cfg = parse(cfgText);
const PAGE = new URL("../../../../src/pages/docs/integrations/frameworks/cloudflare-ai-chat.mdx", import.meta.url);

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
});

test("collector: stamps project_name as a resource attribute, drops storage spans, maps types", () => {
  const res = cfg.processors["resource/future_agi"].attributes;
  assert.deepEqual(res.find((a) => a.key === "project_name"), { key: "project_name", value: "${env:FI_PROJECT_NAME}", action: "upsert" });
  assert.deepEqual(cfg.processors["filter/storage_spans"].traces.span, ['IsMatch(name, "^durable_object_storage_")']);
  const st = cfg.processors["transform/cloudflare_agents"].trace_statements[0].statements.join("\n");
  assert.match(st, /gen_ai\.span\.kind"\], "AGENT"\) where attributes\["gen_ai\.operation\.name"\] == "invoke_agent"/);
  assert.match(st, /STATUS_CODE_ERROR\) where attributes\["error\.type"\] != nil/);
  assert.match(st, /session\.id"\], attributes\["gen_ai\.conversation\.id"\]/);
  assert.match(st, /delete_matching_keys\(attributes, "\^gen_ai\\\\\.usage\\\\\."\) where attributes\["gen_ai\.operation\.name"\] == "invoke_agent"/);
  assert.deepEqual(cfg.service.pipelines.traces.processors, ["filter/storage_spans", "resource/future_agi", "transform/cloudflare_agents", "batch"]);
});

test("collector: content is off unless FI_CAPTURE_CONTENT=true", () => {
  const st = cfg.processors["transform/cloudflare_agents"].trace_statements;
  const span = st[0].statements;
  const contentOn = span.filter((s) => s.includes("input.value") || s.includes("output.value"));
  for (const s of contentOn.filter((s) => s.startsWith("set("))) assert.match(s, /FI_CAPTURE_CONTENT:-false\}" == "true"$/);
  const del = span.find((s) => s.includes("input\\\\.messages"));
  assert.match(del, /tool\\\\\.call\\\\\.arguments\|tool\\\\\.call\\\\\.result/);
  assert.match(del, /FI_CAPTURE_CONTENT:-false\}" != "true"$/);
  assert.deepEqual(st[1], { context: "spanevent", statements: ['keep_keys(attributes, ["exception.type"]) where "${env:FI_CAPTURE_CONTENT:-false}" != "true"'] });
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
  assert.deepEqual(json.migrations[0].new_sqlite_classes, ["SupportChat"]);
  assert.equal(json.vars, undefined, "no vars block: secrets go through `wrangler secret put`");
  assert.doesNotMatch(text, /OPENAI_API_KEY"\s*:/);
});

test("Worker: extends AIChatAgent, traces the AI SDK with payloads off by default, has a tool", () => {
  const src = read("src/index.ts");
  assert.match(src, /class SupportChat extends AIChatAgent<Env>/);
  assert.match(src, /import \{ wrapAISDK \} from "agents\/observability\/ai"/);
  assert.match(src, /storeMessages: this\.env\.STORE_MESSAGES === "true"/);
  assert.match(src, /storeTools: this\.env\.STORE_TOOLS === "true"/);
  assert.match(src, /lookup_order: ai\.tool\(/);
  assert.doesNotMatch(src, /futureagi|X-Api-Key|FI_API_KEY/i, "the Worker never holds Future AGI keys");
  const pkg = JSON.parse(read("package.json"));
  assert.equal(pkg.dependencies["@cloudflare/ai-chat"], "0.12.1", "the fixture depends on @cloudflare/ai-chat itself");
});

test("page shows the shipped files verbatim", { skip: !existsSync(PAGE) && "page not in this checkout" }, () => {
  const page = readFileSync(PAGE, "utf8");
  for (const f of ["otelcol.yaml", "wrangler.jsonc", "src/index.ts"]) {
    assert.ok(page.includes(read(f).trim()), `${f} differs from the page`);
  }
});
