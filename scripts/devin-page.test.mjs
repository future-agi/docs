import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { integrationAids, integrationAliases, integrations } from '../src/lib/integrations.mjs';

const pages = new URL('../src/pages/', import.meta.url);
const href = '/docs/integrations/coding-agents/devin';
const page = readFileSync(new URL(`.${href}.mdx`, pages), 'utf8');

function section(heading) {
  const level = heading.match(/^#+/)[0].length;
  const start = page.indexOf(`${heading}\n`);
  assert.notEqual(start, -1, `Missing section: ${heading}`);
  const body = page.slice(start + heading.length + 1);
  const end = body.search(new RegExp(`^#{1,${level}} `, 'm'));
  return end === -1 ? body : body.slice(0, end);
}

function routeExists(route) {
  return ['.mdx', '.md', '.astro', '/index.mdx', '/index.md', '/index.astro']
    .some(suffix => existsSync(new URL(`.${route}${suffix}`, pages)));
}

test('Devin legacy route points discovery to the coding overview, not a support-status card', () => {
  assert.equal(integrationAids.find(aid => aid.href === href), undefined);
  assert.equal(integrationAliases[href], '/docs/integrations/coding-agents');
  assert.ok(!integrations.some(integration => integration.href === href));
  const about = section('## About');
  assert.match(about, /not supported as a direct Future AGI integration/);
  assert.match(about, /does not automatically send traces to Future AGI/);
  assert.match(about, /no hosted-Devin connection to configure in Future AGI/);
  assert.match(about, /does not collect Devin credentials or poll Devin's APIs/);
});

test('Devin distinguishes native customer-run cloud tracing from hosted export', () => {
  const sdk = section('## Devin SDK tracing');
  assert.match(sdk, /@cognition-ai\/sdk/);
  assert.match(sdk, /both local and cloud sessions as OpenTelemetry spans/);
  assert.match(sdk, /application runs the SDK, authenticates to Devin/);
  assert.match(sdk, /configures the tracer provider and exporter/);
  assert.match(sdk, /https:\/\/docs\.devin\.ai\/sdk\/guides\/tracing/);
  assert.match(sdk, /not a supported Future AGI Devin integration or a server-side export/);
  assert.doesNotMatch(page, /Hosted Devin sends none|no way to trace|all unavailable/i);
});

test('Devin privacy guidance precedes coverage limits and preserves content-off advice', () => {
  const privacy = section('### Content and privacy');
  assert.match(privacy, /Content is recorded by default/);
  assert.match(privacy, /prompts, replies, and tool inputs and outputs/);
  assert.match(privacy, /repository code/);
  assert.match(privacy, /Set `recordContent: false`.*omit that text before exporting/);
  assert.match(privacy, /usage and cost when the session reports them/);
  assert.match(privacy, /manage the Devin credentials in your own application/);
  assert.match(privacy, /not a general-purpose redaction filter/);
  assert.ok(page.indexOf('recordContent: false') < page.indexOf('### Cloud-session limits'));
});

test('Devin documents live-only coverage, turn parentage and missing cloud usage', () => {
  const limits = section('### Cloud-session limits');
  assert.match(limits, /live events only while your process is attached/);
  assert.match(limits, /History replayed on attach or reload is not exported/);
  assert.match(limits, /in-progress turn is traced from the time you attach/);
  assert.match(limits, /Each turn is its own trace unless it has a parent span/);
  assert.match(limits, /`parent` span or the active OpenTelemetry context/);
  assert.match(limits, /Cloud sessions report turns and tool calls, but not per-request token usage or cost/);
  assert.match(limits, /Do not expect model-request generation spans for cloud sessions/);
});

test('Devin support status introduces no connector, credentials, sink or copied hook configuration', () => {
  for (const value of [
    'api.devin.ai', 'tracer/v1/traces', 'api.futureagi.com', 'X-Api-Key',
    'X-Secret-Key', 'project_name', 'hooks.json', 'pre_user_prompt',
    'post_cascade_response', 'trajectory_id', 'emit.py',
  ]) assert.ok(!page.includes(value), `Unexpected setup instruction: ${value}`);
  assert.doesNotMatch(page, /DEVIN_API_KEY\s*=|FI_[A-Z_]*DEVIN|```/);
});

test('Devin alternatives remain true independently of the Desktop guide', () => {
  const alternatives = section('## Other Devin options');
  for (const url of [
    'https://docs.devin.ai/product-guides/session-insights',
    'https://docs.devin.ai/desktop/cascade/hooks',
    'https://docs.devin.ai/cli/extensibility/hooks/lifecycle-hooks',
  ]) assert.ok(alternatives.includes(url), `Missing vendor reference: ${url}`);
  assert.match(alternatives, /not a trace export to Future AGI/);
  assert.match(alternatives, /separate from hosted Devin/);
  assert.match(alternatives, /not described on this page/);
  const desktop = '/docs/integrations/coding-agents/devin-desktop';
  if (!routeExists(desktop)) assert.ok(!page.includes(desktop));
  assert.doesNotMatch(page, /not published|in progress|until it is published|Future AGI supports/);
});

test('Devin next steps resolve and link to supported hook tracing', () => {
  const next = section('## Next Steps');
  for (const route of ['/docs/integrations/coding-agents/cursor', '/docs/integrations/coding-agents/hook-to-otlp']) {
    assert.ok(next.includes(`](${route})`));
  }
  for (const [, route] of page.matchAll(/\]\((\/docs\/[^)#\s]+)/g)) {
    assert.ok(routeExists(route), `Missing internal route: ${route}`);
  }
});

test('Devin public prose has no verification diary or untested-setup presentation', () => {
  assert.doesNotMatch(page, /last checked|verified live|vendor verification|untested|not tested|has not tested|\b20\d{2}-\d{2}-\d{2}\b|test_page\.py|## What would change this/i);
});
