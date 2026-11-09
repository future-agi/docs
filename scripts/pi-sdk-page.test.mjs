import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { integrations } from '../src/lib/integrations.mjs';

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const page = read('../src/pages/docs/integrations/coding-agents/pi-sdk.mdx');
const readme = read('../examples/coding-agents/pi-sdk/README.md');
const examplePath = new URL('../examples/coding-agents/pi-sdk/trace_session.mjs', import.meta.url);
const example = readFileSync(examplePath, 'utf8');
const manifest = JSON.parse(read('../examples/coding-agents/pi-sdk/package.json'));

test('Pi SDK has a separate maintained-package entry from the Pi CLI extension', () => {
  const entry = integrations.find(item => item.id === 'pi-sdk');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/pi-sdk');
  assert.equal(entry.category, 'coding');
  assert.equal(entry.method, 'traceAI SDK');
  assert.notEqual(entry.href, integrations.find(item => item.id === 'pi').href);
  assert.match(page, /wrapCreateAgentSession\(createAgentSession\)/);
  assert.match(page, /instrumentSession\(session\)/);
});

test('Pi SDK guide and example use the same released package versions', () => {
  assert.deepEqual(manifest.dependencies, {
    '@earendil-works/pi-coding-agent': '1.2.0',
    '@traceai/fi-core': '1.1.1',
    '@traceai/pi-coding-agent': '0.1.0',
  });
  for (const [name, version] of Object.entries(manifest.dependencies)) {
    assert.ok(page.includes(`${name}@${version}`), `Missing install pin: ${name}`);
  }
  assert.equal(manifest.engines.node, '>=22.19.0');
  for (const text of [page, readme]) assert.match(text, /Node\.js 22\.19 or newer/);
});

test('Pi SDK customer setup runs an application rather than the QA harness', () => {
  assert.match(page, /node app\.mjs/);
  for (const text of [page, readme]) {
    assert.match(text, /node trace_session\.mjs/);
    assert.doesNotMatch(text, /run_e2e\.sh|TRACEAI_PI_PACKAGE|privacy marker|tested with|read 2026-|E2E evidence|verified live/i);
    assert.match(text, /PI_CODING_AGENT_DIR/);
    assert.match(text, /duplicate traces/);
  }
});

test('Pi SDK privacy keeps error descriptions separate from ordinary outputs', () => {
  for (const text of [page, readme]) {
    assert.match(text, /no status message/);
    assert.match(text, /error\.type/);
    assert.match(text, /does not enable error text by itself/i);
    assert.match(text, /export FI_HIDE_INPUTS=false/);
    assert.match(text, /export FI_HIDE_OUTPUTS=false/);
    assert.match(text, /export FI_HIDE_ERROR_DETAILS=true/);
    assert.match(text, /FI_HIDE_ERROR_DETAILS=false/);
    assert.match(text, /(?:limited summary|limited summaries)/);
    assert.doesNotMatch(text, /By default the status message holds|FI_HIDE_OUTPUTS=false[^\n]*#.*error text/);
  }
  assert.match(page, /requires both `hideOutputs: false` and `hideErrorDetails: false`/);
  assert.match(readme, /requires both `FI_HIDE_OUTPUTS=false` and `FI_HIDE_ERROR_DETAILS=false`/);
  assert.match(page, /hideErrorDetails: true/);
  assert.match(page, /Explicit `traceConfig` values take precedence/);
});

test('Pi SDK application parses and retains read-only tools, failure exit and shutdown', () => {
  const result = spawnSync(process.execPath, ['--check', fileURLToPath(examplePath)], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  for (const text of [example, page]) {
    assert.match(text, /tools: \["read", "ls"\]/);
    assert.match(text, /last\?\.stopReason === "error" \|\| last\?\.stopReason === "aborted"/);
    assert.match(text, /process\.exitCode = 1/);
    assert.match(text, /finally \{\s*session\?\.dispose\(\);\s*await tracerProvider\.shutdown\(\);/);
  }
  assert.match(example, /Set PI_PROVIDER and PI_MODEL together/);
});
