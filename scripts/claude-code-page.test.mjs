import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/coding-agents/claude-code.mdx', import.meta.url), 'utf8');

test('Claude Code keeps its discoverable route and three-step maintained-package setup', () => {
  const entry = integrations.find(item => item.id === 'claude-code');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/claude-code');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'traceAI plugin');
  assert.deepEqual([...page.matchAll(/^## \d\. (.+)$/gm)].map(match => match[1]), [
    'Get your keys', 'Set up tracing', 'Run Claude Code',
  ]);
  assert.match(page, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.match(page, /npx @traceai\/agents setup claude --project coding-agents/);
  assert.match(page, /```bash\nclaude\n```/);
  assert.match(page, /hidden terminal prompts/);
  assert.match(page, /Open \*\*Observe\*\*/);
  assert.match(page, /\*\*Sessions\*\*/);
  assert.doesNotMatch(page, /git clone|otelcol-contrib --config|run_e2e\.sh|verified live|QA harness|release pending|internal hold/i);
});

test('Claude Code documents content-on defaults, a content-off switch and protected configuration', () => {
  const beforeRun = page.split('## 3. Run Claude Code')[0];
  assert.match(beforeRun, /Content capture is \*\*on by default\*\*/);
  assert.match(beforeRun, /--no-capture-content/);
  assert.match(beforeRun, /secrets the agent reads/);
  for (const setting of [
    'FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'FI_AGENT_CAPTURE_CONTENT=false',
    'FI_AGENT_ENABLED=false', 'FI_USER_ID', 'FI_BASE_URL', 'FI_OTLP_ENDPOINT',
    'CLAUDE_CONFIG_DIR', 'FI_AGENT_CONFIG_DIR', 'FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS',
    '~/.claude/settings.json', '~/.claude/futureagi.json', 'futureagi/agents/credentials.json',
    '--scope project', '--project-dir /path/to/repository', '--user-only',
  ]) assert.ok(page.includes(setting), setting);
  assert.match(page, /repository cannot redirect saved credentials to an unapproved destination/);
  assert.match(page, /without credentials/);
  assert.match(page, /Redaction cannot guarantee removal of arbitrary secrets/);
  assert.match(page, /does not backfill/);
});

test('Claude Code retains trace semantics, lifecycle and actionable migration guidance', () => {
  for (const command of ['status', 'doctor', 'disable', 'enable', 'update', 'uninstall']) {
    assert.ok(page.includes(`npx @traceai/agents ${command} claude`), command);
  }
  for (const field of ['One trace per prompt', 'cache-read/cache-write', 'Subagents', 'failure status']) {
    assert.ok(page.includes(field), field);
  }
  assert.match(page, /completed turn and final answer.*next human prompt arrives or the session ends/);
  assert.match(page, /not measured API latency/);
  assert.match(page, /does not report Anthropic billing costs/);
  assert.match(page, /--no-session-persistence/);
  for (const diagnostic of ['NATIVE_TRACING_CONFLICT', 'HOST_HOOKS_DISABLED', 'PROJECT_CONFIG_IGNORED', 'RUNTIME_MISSING_OR_CHANGED', 'AUTH_REJECTED']) {
    assert.ok(page.includes(diagnostic), diagnostic);
  }
  for (const flag of ['CLAUDE_CODE_ENHANCED_TELEMETRY_BETA', 'ENABLE_ENHANCED_TELEMETRY_BETA', 'ENABLE_BETA_TRACING_DETAILED']) {
    assert.ok(page.includes(flag), flag);
  }
  assert.match(page, /without removing unrelated hooks/);
  assert.match(page, /No background service is installed/);
  assert.match(page, /Delivery is best effort/);
});
