import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../src/pages/docs/integrations/traceai/openlit.mdx", import.meta.url),
  "utf8",
);

test("OpenLIT uses the Cloud OTLP base URL, not the origin or full trace URL", () => {
  const endpoint = source.match(/^export OTEL_EXPORTER_OTLP_ENDPOINT="([^"]+)"/m)?.[1];
  assert.equal(endpoint, "https://api.futureagi.com/tracer");
  assert.doesNotMatch(source, /origin only|origin, with no path|Use the origin only/);
  assert.match(source, /https:\/\/api\.futureagi\.com\/tracer\/v1\/traces/);
  assert.match(source, /Do not include `\/v1\/traces`/);
  assert.match(source, /self-hosted/i);
});

test("OpenLIT keeps native tracing and the privacy and duplicate-span guidance", () => {
  assert.match(source, /openlit\.init\(/);
  assert.match(source, /capture_message_content=False/);
  assert.match(source, /disable_metrics=True/);
  assert.match(source, /disable_events=True/);
  assert.match(source, /pricing_json=os\.environ\["OPENLIT_PRICING_JSON"\]/);
  assert.match(source, /project_name=my-chatbot,project_type=observe/);
  for (const key of ["FI_API_KEY", "FI_SECRET_KEY"]) {
    assert.ok(source.includes(`quote(os.environ["${key}"], safe="")`));
  }
  assert.match(source, /not a full privacy switch/);
  assert.match(source, /gen_ai\.tool\.args/);
  assert.match(source, /gen_ai\.request\.user/);
  assert.match(source, /provider's error body/);
  assert.match(source, /Pick one/);
  assert.match(source, /OTEL_EXPORTER_OTLP_TRACES_ENDPOINT/);
});
