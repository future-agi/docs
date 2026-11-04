import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const read = file => fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const guide = read('src/pages/docs/integrations/traceai/genkit-go.mdx');
const reference = read('src/pages/docs/sdk/tracing/environment-variables.mdx');

test('Genkit Go and the shared reference scope privacy to supported coarse switches', () => {
  assert.doesNotMatch(reference, /All languages read from the same set/);
  assert.match(reference, /Support varies by language and integration/);
  assert.match(reference, /## Genkit Go privacy/);
  assert.match(guide, /environment-variables#genkit-go-privacy/);
  for (const page of [guide, reference]) {
    for (const flag of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS', 'FI_HIDE_INPUT_MESSAGES', 'FI_HIDE_OUTPUT_MESSAGES']) {
      assert.ok(page.includes(flag), flag);
    }
    assert.match(page, /[Gg]ranular privacy flags[\s\S]*?have no effect in this adapter/);
    assert.match(page, /system instructions/);
    assert.match(page, /[Kk]eep `FI_HIDE_ERROR_DETAILS=true`/);
    assert.match(page, /[Gg]ranular flags do not enable this default|They also do not enable the default error redaction/);
    assert.match(page, /false`[\s\S]*?even (?:with|when) a coarse hide switch/);
    assert.match(page, /console output/);
  }
  assert.match(guide, /error details are hidden only if `FI_HIDE_INPUTS` or `FI_HIDE_OUTPUTS` is true/);
  assert.match(reference, /True when either coarse hide switch is true; otherwise False/);
  assert.match(reference, /`ConfigFromEnv\(\)` reads only these three privacy switches/);
  assert.match(reference, /`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, not `FI_BASE_URL`/);
});

test('Genkit Go pins its maintained adapter and uses the current Gemini replacement', () => {
  assert.match(guide, /github\.com\/future-agi\/traceAI\/go\/genkit@v0\.1\.0/);
  assert.doesNotMatch(guide, /genkit@(?:dev|main|latest)/);
  assert.match(guide, /ai\.WithModelName\("googleai\/gemini-3\.5-flash-lite"\)/);
  assert.doesNotMatch(guide, /gemini-2\.5-flash/);
  assert.match(guide, /ContentCapturingMode: otelgenai\.NoContent/);
  assert.match(guide, /CaptureActionIO:\s+false/);
  for (const flag of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS']) {
    assert.ok(guide.includes(`export ${flag}=true`), flag);
  }
});
