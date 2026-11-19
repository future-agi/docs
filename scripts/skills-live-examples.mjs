#!/usr/bin/env node
// Usage (cloud lane): node scripts/skills-live-examples.mjs DOCS_ROOT SDK_PYTHON NODE_DIR_WITH_SDK
// Cloud-only: publish a neutral support-policy skill on the isolated localhost stack, issue a
// read-only consume credential, then run the docs' application examples unmodified through the
// docs test (SKILLS_DOCS_LIVE=1). The credential stays in this process's child environment only.
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
const api = 'http://localhost:8100';
const [docs, python, nodeCwd] = process.argv.slice(2);
const call = async (method, route, body, headers = {}) => {
  const r = await fetch(api + route, { method, headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID(), ...headers }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const text = await r.text(); let v; try { v = JSON.parse(text); } catch { v = text; }
  if (!r.ok) throw new Error(`${method} ${route}: ${r.status}`);
  return v?.result ?? v;
};
const email = `jordan.ellis.${crypto.randomUUID().slice(0, 5)}@northwind.example`;
const password = `Docs-${crypto.randomUUID()}`;
await call('POST', '/accounts/e2e/clean-signup/', { email, password, full_name: 'Jordan Ellis' });
const tokens = await call('POST', '/accounts/token/', { email, password, remember_me: true });
const auth = { Authorization: `Bearer ${tokens.access}` };
const info = await call('GET', '/accounts/user-info/', undefined, auth);
const h = { ...auth, 'X-Organization-Id': info.organization.id, 'X-Workspace-Id': info.default_workspace_id };
const content = "---\nname: support-policy\ndescription: Use when answering refund or return questions using the team's reviewed support policy.\n---\n# Support policy\n\nAsk for the order date and the reason. Escalate exceptions to a human reviewer.\n";
const published = await call('POST', '/model-hub/skills/publish/', { files: [{ path: 'SKILL.md', content }], labels: ['production'], expected_release_revision: 0, acknowledge_warnings: true }, h);
const issued = await call('POST', '/model-hub/skills/contexts/credentials/', { purpose: 'consume', binding_ids: [],
  grants: [{ kind: 'skill', resource_id: published.skill.id, labels: ['production'], version_ids: [published.version.id] }],
  expires_at: new Date(Date.now() + 3600000).toISOString() }, h);
const env = { ...process.env, SKILLS_DOCS_LIVE: '1', SKILLS_DOCS_PYTHON: python, SKILLS_DOCS_NODE_CWD: nodeCwd,
  FI_CONTEXT_CREDENTIAL: issued.secret, FI_CONTEXT_ORIGIN: api, FI_CONTEXT_WORKSPACE_ID: info.default_workspace_id,
  FI_CONTEXT_ORGANIZATION_ID: info.organization.id, SKILLS_DOCS_EXPECT_VERSION_ID: published.version.id };
const run = spawnSync(process.execPath, ['--test', '--test-name-pattern=application example', 'scripts/skills-docs.test.mjs'], { cwd: docs, env, encoding: 'utf8' });
await call('DELETE', `/model-hub/skills/contexts/credentials/${issued.id}/`, undefined, h);
// A child killed by a signal or unable to start has no exit status. It did not pass.
const exit = run.status ?? 1;
const out = (run.stdout ?? '').split('\n').filter((l) => /^(ok |not ok |# (pass|fail|skipped) )/.test(l));
console.log(JSON.stringify({ product_version_id: published.version.id, digest: published.version.digest, exit, summary: out }, null, 2));
process.exitCode = exit;
