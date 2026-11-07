import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/github-copilot.mdx', import.meta.url), 'utf8');
test('Copilot setup uses the maintained launcher with matching host and defaults', () => {
  assert.match(page, /@github\/copilot@1\.0\.106/);
  assert.match(page, /npx @traceai\/agents setup copilot --project coding-agents/);
  assert.match(page, /npx @traceai\/agents run copilot/);
  assert.equal((page.match(/<Step title=/g) || []).length, 3);
  assert.match(page, /on by default/);
  assert.match(page, /--no-capture-content/);
  assert.match(page, /session\.id/);
  assert.doesNotMatch(page, /1\.0\.98|copilot\(\)\s*\{|copilot-otel\.sh|~\/\.zshrc/);
});
test('Copilot page explains recovery, privacy, scope and diagnosis', () => {
  for (const term of ['--replace-credentials', '--scope project', '--project-dir', '--user-only',
    'status copilot --check', 'doctor copilot', 'disable copilot', 'enable copilot', 'uninstall copilot',
    'FI_AGENT_ENABLED=false', 'FI_HIDE_ERROR_DETAILS=true', '0600', 'FI_OTLP_ENDPOINT',
    '~/.copilot/futureagi.json', '~/.config/futureagi/agents/credentials.json',
    'PROJECT_CONFIG_UNSAFE'])
    assert.ok(page.includes(term), term);
  assert.match(page, /unchanged until the new keys validate/);
  assert.match(page, /cannot redirect saved or environment-supplied credentials/);
  assert.match(page, /not a security sandbox/);
  assert.match(page, /Disable stops Copilot tracing across your user and project profiles/);
});
test('Copilot page describes trace contents and separates the unavailable VS Code surface', () => {
  for (const term of ['Each prompt', 'token usage', 'tool calls', 'subagent', 'user.id'])
    assert.ok(page.includes(term), term);
  assert.match(page, /## VS Code Copilot\s+Tracing for VS Code Copilot Chat and inline completions is \*\*not yet available\*\*/);
  assert.doesNotMatch(page, /setup copilot-vscode|Live vendor verification|E2B|run ids|HOLD/);
});
