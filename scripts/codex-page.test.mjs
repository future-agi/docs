import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/coding-agents/codex.mdx', import.meta.url), 'utf8');

test('Codex CLI has a registered native-plugin route distinct from the SDK', () => {
  assert.deepEqual(
    integrations.filter(entry => entry.id === 'codex').map(({ href, category, method, logo }) => ({ href, category, method, logo })),
    [{ href: '/docs/integrations/coding-agents/codex', category: 'coding', method: 'Native plugin', logo: 'openai' }],
  );
  assert.match(page, /\[Codex SDK integration\]\(\/docs\/integrations\/coding-agents\/codex-sdk\)/);
});

test('Codex CLI quick start uses one maintained setup command and native hook review', () => {
  // Three-step layout is enforced by coding-agents-contract.test.mjs.
  assert.match(page, /https:\/\/app\.futureagi\.com\/dashboard\/keys/);
  assert.match(page, /npx @traceai\/agents setup codex --project coding-agents/);
  assert.match(page, /without echoing/);
  assert.match(page, /TRUST_REQUIRED/);
  assert.match(page, /\/hooks/);
  assert.match(page, /codex exec "Read README\.md and summarize the setup steps\."/);
  assert.match(page, /\*\*Observe\*\*/);
  assert.doesNotMatch(page, /git clone|curl .+\|\s*(?:sh|bash)|hook-emitter|copy.*(?:hook|emitter) script/i);
});

test('Codex CLI describes per-prompt traces, model usage, tools, subagents and sessions honestly', () => {
  for (const term of ['each Codex prompt', 'codex.model_attempt', 'tool calls', 'codex.subagent', 'nested children', '**Sessions**']) {
    assert.ok(page.includes(term), term);
  }
  assert.match(page, /not a complete provider request body/);
  assert.match(page, /reconstructed from Codex's rollout when available/);
  assert.match(page, /not counted again on the parent trace/);
  assert.match(page, /costs are omitted when Codex does not report them/);
});

test('Codex CLI documents default-on capture, opt-out and protected configuration', () => {
  assert.match(page, /Content capture is on by default/);
  assert.match(page, /--no-capture-content/);
  assert.match(page, /FI_AGENT_CAPTURE_CONTENT=false/);
  assert.match(page, /FI_HIDE_ERROR_DETAILS/);
  assert.match(page, /~\/\.config\/futureagi\/agents\/credentials\.json/);
  assert.match(page, /\$CODEX_HOME\/futureagi\.json/);
  assert.match(page, /~\/\.codex\/futureagi\.json/);
  assert.match(page, /\.codex\/futureagi\.json/);
  const override = page.match(/```json\n([\s\S]*?)\n```/)?.[1];
  assert.ok(override);
  assert.deepEqual(JSON.parse(override), { schemaVersion: 1, captureContent: false });
  assert.match(page, /DESTINATION_NOT_APPROVED/);
  assert.match(page, /cannot increase your saved privacy setting/);
  assert.match(page, /Redaction cannot guarantee/);
});

test('Codex CLI separates destination, user installation and invocation-only scope', () => {
  assert.match(page, /`--project coding-agents` names the destination/);
  assert.match(page, /`--scope project` is not supported/);
  assert.match(page, /`--user-only`/);
  assert.match(page, /does not disable repository settings in subsequent Codex hooks/);
  assert.match(page, /`--project-dir <path>`/);
  assert.match(page, /PROJECT_CONFIG_IGNORED/);
});

test('Codex CLI covers management commands and preserves uninstall credentials', () => {
  for (const command of ['status', 'doctor', 'disable', 'enable', 'uninstall']) {
    assert.ok(page.includes(`npx @traceai/agents ${command} codex`), command);
  }
  assert.match(page, /preserves saved credentials, preexisting settings, and your edits/);
  assert.match(page, /AUTH_REJECTED/);
  assert.match(page, /NODE_INTERPRETER_MISSING/);
});

test('Codex CLI keeps supported surface limits without public engineering diaries or fake media', () => {
  assert.match(page, /0\.167\.0/);
  assert.match(page, /Linux/);
  assert.match(page, /22\.16/);
  assert.match(page, /Hosted Codex task tracing is \*\*not yet available\*\*/);
  assert.doesNotMatch(page, /verified live|QA runner|test date|REGISTRY_PUBLICATION_REQUIRED|TH-8228|PR #932|int-codex|fixture|placeholder image/i);
});
