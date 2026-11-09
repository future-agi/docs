import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import http from "node:http";
import { fileURLToPath } from "node:url";
import test from "node:test";

const example = fileURLToPath(new URL("../", import.meta.url));
const attributes = (items = []) => Object.fromEntries(items.map(({ key, value }) => [key, Object.values(value)[0]]));

async function runApp(overrides = {}) {
  const payloads = [];
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    assert.equal(req.url, "/tracer/v1/traces");
    payloads.push(JSON.parse(Buffer.concat(chunks).toString()));
    res.setHeader("Content-Type", "application/json");
    res.end("{}");
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    const result = await new Promise(resolve => execFile(process.execPath, [
      "--import", "./test/fixture.mjs", "--import", "@traceai/auto/register", "app.mjs",
    ], {
      cwd: example,
      timeout: 20_000,
      env: {
        ...process.env,
        CLOUDFLARE_ACCOUNT_ID: "test-account",
        CLOUDFLARE_API_TOKEN: "synthetic-cloudflare-token",
        FI_API_KEY: "synthetic-fi-api-key",
        FI_SECRET_KEY: "synthetic-fi-secret-key",
        FI_PROJECT_NAME: "workers-ai",
        FI_BASE_URL: `http://127.0.0.1:${server.address().port}`,
        FI_HIDE_INPUTS: "false",
        FI_HIDE_OUTPUTS: "false",
        FI_HIDE_ERROR_DETAILS: "false",
        OTEL_SDK_DISABLED: "false",
        ...overrides,
      },
    }, (error, stdout, stderr) => resolve({ code: error?.code ?? 0, stdout, stderr })));
    const resources = payloads.flatMap(payload => payload.resourceSpans ?? []);
    const spans = resources.flatMap(resource => resource.scopeSpans.flatMap(scope => scope.spans));
    const exported = JSON.stringify(payloads);
    for (const secret of ["synthetic-cloudflare-token", "synthetic-fi-api-key", "synthetic-fi-secret-key", "test-account"]) {
      assert.ok(!exported.includes(secret), "OTLP must not contain credentials or the account ID");
    }
    return { ...result, resources, spans, exported };
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test("published preload exports one model span and provider usage on natural exit", async () => {
  const result = await runApp();
  assert.equal(result.code, 0, result.stderr);
  assert.match(result.stdout, /Hello-fixture!/);
  assert.equal(result.spans.length, 1);
  const span = result.spans[0];
  const attrs = attributes(span.attributes);
  assert.equal(attrs["gen_ai.provider.name"], "cloudflare.workers_ai");
  assert.equal(attrs["gen_ai.request.model"], "@cf/meta/llama-3.2-1b-instruct");
  assert.equal(Number(attrs["gen_ai.usage.input_tokens"]), 12);
  assert.equal(Number(attrs["gen_ai.usage.output_tokens"]), 4);
  assert.equal(attrs["traceai.capture.layer"], "wire");
  assert.equal(span.status.code, 1);
  assert.match(result.exported, /Say hello in one word\./);
  assert.match(result.exported, /Hello-fixture!/);
  assert.equal(attributes(result.resources[0].resource.attributes).project_name, "workers-ai");
});

test("hide flags remove prompt and output while preserving usage", async () => {
  const result = await runApp({ FI_HIDE_INPUTS: "true", FI_HIDE_OUTPUTS: "true", FI_HIDE_ERROR_DETAILS: "true" });
  assert.equal(result.code, 0, result.stderr);
  assert.equal(result.spans.length, 1);
  assert.doesNotMatch(result.exported, /Say hello in one word\.|Hello-fixture!/);
  assert.equal(Number(attributes(result.spans[0].attributes)["gen_ai.usage.output_tokens"]), 4);
});

test("HTTP failure exports ERROR and returns a nonzero exit without logging response details", async () => {
  const result = await runApp({ TEST_HTTP_STATUS: "403", FI_HIDE_INPUTS: "true", FI_HIDE_OUTPUTS: "true", FI_HIDE_ERROR_DETAILS: "true" });
  assert.equal(result.code, 1);
  assert.match(result.stderr, /Workers AI request failed \(HTTP 403\)/);
  assert.doesNotMatch(result.stderr, /synthetic-cloudflare-token|Say hello/);
  assert.equal(result.spans.length, 1);
  assert.equal(result.spans[0].status.code, 2);
  assert.doesNotMatch(result.exported, /Say hello in one word\./);
});

test("missing Cloudflare credentials fail before the model request", async () => {
  const result = await runApp({ CLOUDFLARE_API_TOKEN: "" });
  assert.equal(result.code, 1);
  assert.match(result.stderr, /Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN/);
  assert.equal(result.spans.length, 0);
});

test("page ships the exact app and maintained-package install, not a copied tracer", async () => {
  const page = await readFile(new URL("../../../../src/pages/docs/integrations/runtimes/cloudflare-workers-ai.mdx", import.meta.url), "utf8");
  const app = await readFile(new URL("../app.mjs", import.meta.url), "utf8");
  assert.equal(page.match(/```javascript\n([\s\S]*?)```/)[1], app);
  assert.match(page, /npm install @traceai\/auto@0\.1\.2/);
  assert.match(page, /node --import @traceai\/auto\/register app\.mjs/);
  assert.match(page, /captured by default/);
  assert.match(page, /does not run inside a deployed Worker/);
  assert.doesNotMatch(page, /src\/tracing\.ts|wrangler dev|run_e2e\.sh|Live vendor verification|2026-/);
});
