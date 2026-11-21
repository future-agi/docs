import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { integrations, integrationNavigation } from '../src/lib/integrations.mjs';

const read = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/traceai/auto.mdx');
const route = '/docs/integrations/traceai/auto';

test('zero-code Node guide is discoverable from the catalog, sidebar and setup paths', () => {
  const entry = integrations.find(item => item.id === 'traceai-auto');
  assert.equal(entry?.href, route);
  assert.equal(entry?.category, 'frameworks');
  assert.ok(entry?.aliases.includes('@traceai/auto'));
  assert.ok(JSON.stringify(integrationNavigation).includes(route));
  for (const file of ['quickstart/setup-observability', 'integrations/traceai/index']) {
    assert.ok(read(`src/pages/docs/${file}.mdx`).includes(route));
  }
});

test('primary setup preloads a maintained package without app instrumentation', () => {
  assert.match(page, /Node\.js 20\.6 or later/);
  assert.match(page, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.match(page, /<Steps>[\s\S]*<Step title="Install the package">/);
  for (const command of ['npm install @traceai/auto', 'node --import @traceai/auto/register app.mjs', 'NODE_OPTIONS="--import @traceai/auto/register" npm start', 'node --require @traceai/auto/register app.cjs', 'npx --no-install traceai-auto doctor']) {
    assert.ok(page.includes(command), command);
  }
  const examples = [...page.matchAll(/```javascript\n([\s\S]*?)\n```/g)];
  assert.equal(examples.length, 2);
  assert.match(examples[0][1], /import OpenAI from "openai"/);
  assert.doesNotMatch(examples[0][1], /traceai|opentelemetry|instrument|register/);
  assert.match(page, /Open \*\*Observe\*\*[\s\S]*select `ridgeline-support`/);
  assert.match(page, /zero exit code alone does not prove export health/);
});

test('routing example contrasts separate providers with explicit app-span forwarding', () => {
  assert.match(page, /npm install @traceai\/auto@0\.4\.1/);
  for (const mode of ['true', 'false']) assert.ok(page.includes(`FI_FORWARD_APP_SPANS=${mode} node support-request.mjs`));
  assert.match(page, /provider\.register\(\);\s+await import\("@traceai\/auto\/register"\)/);
  assert.match(page, /startActiveSpan\("support\.answer"/);
  assert.match(page, /SDK starts after the agent/);
});

test('HTTP and Genkit explain selective export and the role of the global provider', () => {
  assert.match(page, /FI_INSTRUMENTATIONS=openai,wire,http/);
  assert.match(page, /Installing the HTTP package alone does nothing/);
  assert.match(page, /only if it sees an AI span in the same trace/);
  assert.match(page, /FI_DISABLED_INSTRUMENTATIONS=http/);
  assert.match(page, /Genkit creates native spans on the global provider/);
  assert.match(page, /`genkit` reports `manual`/);
});

test('privacy defaults, runtime boundaries and reference links remain explicit', () => {
  const setup = page.split('## Try a minimal')[0];
  assert.match(setup, /captured by default/);
  for (const flag of ['FI_HIDE_INPUTS=true', 'FI_HIDE_OUTPUTS=true', 'FI_HIDE_ERROR_DETAILS=true']) assert.ok(setup.includes(flag));
  assert.match(page, /PII pattern redaction[^\n]*off by default/);
  assert.match(page, /does not enable base64 image export/);
  assert.match(page, /Other exporters retain their own privacy policies/);
  assert.match(page, /README\.md#library-coverage/);
  for (const anchor of ['nextjs', 'node-server-bundlers', 'aws-lambda-and-short-lived-processes', 'edge-and-browsers']) assert.ok(page.includes(`FRAMEWORKS.md#${anchor}`));
  assert.match(page, /application-owned exporter/);
  assert.match(page, /\/docs\/sdk\/tracing\/set-up-tracing/);
  assert.doesNotMatch(page, /verified live|PASS\/FAIL|loopback|test harness|E2B|not tested/);
  const image = page.match(/!\[[^\]]+\]\((\/images\/[^)]+)\)/)?.[1];
  assert.ok(image);
  assert.ok(existsSync(new URL(`../public${image}`, import.meta.url)));
  assert.match(page, /`true`, `1`, `yes`, `on` or `false`, `0`, `no`, `off`/);
  assert.match(page, /## Next steps/);
});
