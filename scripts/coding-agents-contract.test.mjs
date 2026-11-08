import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { integrations, integrationAids, integrationNavigation, integrationAliases } from '../src/lib/integrations.mjs';

const directory = new URL('../src/pages/docs/integrations/coding-agents/', import.meta.url);
const read = name => readFileSync(new URL(name, directory), 'utf8');
const pages = {
  'claude-code': ['claude'], codex: ['codex'], cursor: ['cursor'],
  'github-copilot': ['copilot'], 'google-antigravity': ['antigravity'],
  'grok-build': ['grok'], opencode: ['opencode', 'opencode-v1'],
  goose: ['goose'], 'hermes-agent': ['hermes'], openclaw: ['openclaw'],
  pi: ['pi'], 'oh-my-pi': ['oh-my-pi'],
};
const headings = ['What it traces', 'Before you start', 'Quick start', 'Configuration',
  'User and project scope', 'Manage tracing', 'Troubleshooting', 'Privacy'];
const steps = ['Get your Future AGI keys', 'Set up tracing', 'Run the agent and open the trace'];
const envs = ['FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'FI_AGENT_CAPTURE_CONTENT=false',
  'FI_AGENT_ENABLED=false', 'FI_USER_ID', 'FI_BASE_URL', 'FI_OTLP_ENDPOINT', 'FI_AGENT_CONFIG_DIR'];
const section = (text, name) => text.split(`## ${name}\n`)[1]?.split(/\n## /)[0] ?? '';
const configTable = text => section(text, 'Configuration').match(/^\| Setting \| Purpose \|\n(?:\|[^\n]*\n?)+/m)?.[0].trim();
const baselineTable = configTable(read('claude-code.mdx'));
const overview = read('index.mdx');

// Shared layout checks live here; page-specific suites retain host behavior assertions.
for (const [slug, agents] of Object.entries(pages)) {
  test(`${slug}: uniform coding-agent documentation contract`, () => {
    const text = read(`${slug}.mdx`);
    const actual = [...text.matchAll(/^## (.+)$/gm)].map(m => m[1]);
    assert.deepEqual(actual.filter(h => headings.includes(h)), headings);
    for (const heading of headings) assert.equal(actual.filter(h => h === heading).length, 1, heading);
    const quick = section(text, 'Quick start');
    assert.deepEqual([...quick.matchAll(/<Step title="([^"]+)">/g)].map(m => m[1]), steps);
    assert.equal((quick.match(/<\/Step>/g) ?? []).length, 3);
    assert.ok(quick.includes('https://app.futureagi.com/dashboard/keys'));
    for (const agent of agents) {
      const command = `npx @traceai/agents setup ${agent} --project coding-agents`;
      assert.ok(quick.includes(command), command);
      assert.ok(overview.includes(command), `${agent} overview command`);
    }
    for (const command of ['status', 'doctor', 'disable', 'enable', 'update', 'uninstall']) {
      assert.ok(section(text, 'Manage tracing').includes(`npx @traceai/agents ${command} ${agents[0]}`), command);
    }
    const config = section(text, 'Configuration');
    assert.ok(baselineTable);
    assert.equal(configTable(text), baselineTable, 'Shared configuration wording must not drift');
    for (const env of envs) assert.ok(configTable(text).includes('`' + env), env);
    assert.ok(config.includes('Content capture is **on by default**'));
    assert.ok(config.includes('--no-capture-content'));
    assert.ok(text.includes('futureagi/agents/credentials.json'));
    assert.match(text, /owner-only|0600/);
    assert.ok(section(text, 'User and project scope').includes('--user-only'));
    assert.ok(section(text, 'User and project scope').includes('--project-dir'));
    assert.match(section(text, 'Privacy'), /best.effort|not a general secret|redaction cannot|redaction is not a guarantee/i);
    assert.doesNotMatch(text, /verified live|QA harness|run[_-]ids?|PASS\/FAIL|placeholder image|REGISTRY_PUBLICATION_REQUIRED/i);
    const catalog = integrations.find(i => i.href === `/docs/integrations/coding-agents/${slug}`);
    assert.equal(catalog?.category, 'coding');
    for (const [, src] of text.matchAll(/(?:!\[[^\]]*\]\(|src=["'])(\/images\/[^)"']+)/g)) {
      assert.ok(existsSync(new URL(`../public${src}`, import.meta.url)), src);
    }
  });
}

test('all maintained setup pages participate in the shared contract', () => {
  const actual = readdirSync(directory).filter(f => f.endsWith('.mdx') && f !== 'index.mdx')
    .filter(f => /npx @traceai\/agents setup [a-z]/.test(read(f))).map(f => f.replace(/\.mdx$/, '')).sort();
  assert.deepEqual(actual, Object.keys(pages).sort());
});

test('overview distinguishes available surfaces from held surfaces and retired recipes', () => {
  assert.match(overview, /\| Agent \| Setup command \| What is captured \| Status \|/);
  assert.ok(integrationAids.some(a => a.href === '/docs/integrations/coding-agents' && a.category === 'coding'));
  const codingNav = integrationNavigation.find(n => n.title === 'Coding agents');
  assert.ok(codingNav);
  assert.doesNotMatch(JSON.stringify(codingNav), /support status|Hook-to-OTLP emitter|hook-to-otlp/);
  for (const route of ['/docs/integrations/coding-agents/hook-to-otlp', '/docs/integrations/coding-agents/devin', '/docs/integrations/deepseek-harness']) {
    assert.equal(integrationAliases[route], '/docs/integrations/coding-agents');
  }
  for (const name of ['VS Code Copilot', 'Antigravity desktop app (Windows, Linux)', 'Cursor Cloud', 'Hosted Codex', 'DeepSeek Harness']) {
    const row = overview.split('\n').find(line => line.startsWith(`| ${name} |`));
    assert.ok(row?.endsWith('| Not yet available |'), name);
    assert.ok(row.includes('| — |'), 'Held surfaces must not advertise runnable setup');
  }
  assert.match(overview, /best effort/);
  for (const [name, agent] of [['Antigravity desktop app (macOS)', 'antigravity']]) {
    const row = overview.split('\n').find(line => line.startsWith(`| [${name}]`));
    assert.ok(row?.endsWith('| Available |'), name);
    assert.ok(row.includes(`npx @traceai/agents setup ${agent} --project coding-agents`), name);
  }
});
