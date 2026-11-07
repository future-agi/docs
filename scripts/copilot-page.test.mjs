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
test('Copilot page describes trace contents and the VS Code extension surface', () => {
  for (const term of ['Each prompt', 'token usage', 'tool calls', 'subagent', 'user.id'])
    assert.ok(page.includes(term), term);
  assert.ok(page.split('## Quick start')[1].includes('npx @traceai/agents setup copilot-vscode --project coding-agents'));
  const vscode = page.split('## VS Code Copilot\n')[1]?.split('\n## ')[0] ?? '';
  for (const term of ['settingsSync.ignoredSettings', 'Restricted Mode', 'Inline completions are not traced', 'not yet available'])
    assert.ok(vscode.includes(term), term);
  assert.match(page, /never written to VS Code settings/);
  assert.match(page, /restores your VS Code settings exactly/);
  assert.match(page, /npx @traceai\/agents disable copilot-vscode/);
  assert.doesNotMatch(page, /Live vendor verification|E2B|run ids|HOLD/);
});
