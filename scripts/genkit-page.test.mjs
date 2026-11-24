import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/genkit.mdx', import.meta.url), 'utf8');
const setup = page.split('## 3. Configure tracing and run a flow')[1]?.split('## 4. View the trace')[0];
const example = setup?.match(/```javascript\n([\s\S]*?)\n```/)?.[1];

test('Genkit is discoverable as a maintained framework integration', () => {
  const entry = integrations.find(item => item.id === 'genkit');
  assert.equal(entry?.href, '/docs/integrations/traceai/genkit');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI SDK');
  assert.match(page, /\*\*Observe\*\*[\s\S]*`my-genkit-app`[\s\S]*`weatherFlow`/);
});

test('Genkit primary recipe uses published packages and the OpenAI plugin', () => {
  assert.match(page, /npm install @traceai\/genkit@0\.1\.0 @traceai\/fi-core@1\.1\.1 genkit@1\.42\.0 @genkit-ai\/compat-oai@1\.42\.0/);
  assert.match(page, /export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"/);
  assert.match(example, /import \{ openAI \} from "@genkit-ai\/compat-oai\/openai";/);
  assert.match(example, /plugins: \[openAI\(\)\], model: openAI\.model\("gpt-4\.1-nano"\)/);
  assert.match(example, /ai\.defineTool\([\s\S]*ai\.defineFlow\([\s\S]*tools: \[getWeather\]/);
  assert.match(page, /node genkit-app\.mjs/);
  assert.doesNotMatch(page, /GEMINI_API_KEY|googleAI\.model|gemini-3\.[78]-flash/);
});

test('Genkit owns telemetry and flushes both successful and failing flows', () => {
  assert.ok(example.indexOf('from "genkit"') < example.indexOf('await enableTelemetry('));
  assert.match(example, /import \{ enableTelemetry, flushTracing \} from "genkit\/tracing";/);
  assert.match(example, /setGlobalTracerProvider: false/);
  assert.match(example, /spanProcessors: \[new FIGenkitSpanProcessor\(\{ tracerProvider \}\)\]/);
  assert.ok(example.indexOf('await enableTelemetry(') < example.indexOf('ai.defineFlow('));
  assert.match(example, /flushOnSignals\(flushTracing\);/);
  assert.match(example, /try \{[\s\S]*weatherFlow\("Lisbon"\)[\s\S]*\} finally \{[\s\S]*await flushTracing\(\);/);
  assert.match(page, /Do not also register `@traceai\/openai`/);
  const prerequisites = page.split('## 1. Install')[0];
  assert.match(prerequisites, /Do not combine[\s\S]*enableFirebaseTelemetry\(\)[\s\S]*enableGoogleCloudTelemetry\(\)[\s\S]*ENABLE_FIREBASE_MONITORING=true/);
});

test('Genkit explains privacy boundaries without a public verification diary', () => {
  assert.match(page.split('## 3. Configure tracing')[0], /captured by default/);
  assert.match(page, /export FI_HIDE_INPUTS=true/);
  assert.match(page, /export FI_HIDE_OUTPUTS=true/);
  assert.match(page, /With either flag enabled, error messages are also redacted/);
  assert.match(page, /FI_PII_REDACTION` is not applied/);
  assert.match(page, /Dev UI and other exporters still receive the original, unredacted spans/);
  assert.match(page, /npm install @opentelemetry\/api@1\.9\.0/);
  const sessions = page.split('## Sessions')[1]?.split('## Captured spans')[0];
  assert.match(sessions, /setUser\(setSession\(context\.active\(\), \{ sessionId: "chat-123" \}\), \{ userId: "user-42" \}\)/);
  assert.match(sessions, /try \{[\s\S]*context\.with\([\s\S]*\} finally \{[\s\S]*await flushTracing\(\);/);
  assert.doesNotMatch(page, /tested with|not tested|verified live|end-to-end runs|quota.*exhausted|alpha\.|2026-10-16/i);
});
