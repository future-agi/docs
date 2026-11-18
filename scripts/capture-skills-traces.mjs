#!/usr/bin/env node
/**
 * Cloud-only capture of the skill-trace views at 1440x900 for the documentation.
 * Run on the VM against the isolated localhost standalone E2E stack, with the product's
 * native-runtime emitter and an interpreter that has the SDK (futureagi 0.8.0) and traceAI:
 *   SKILLS_DOCS_EMITTER=<product>/e2e/stack/native-runtime/emit.py SKILL_TRACES_PYTHON=<python> \
 *     node scripts/capture-skills-traces.mjs OUT_DIR
 * The application reads skills through the real SDK inside traced requests; nothing is
 * written to spans by hand. All names are neutral synthetic fixtures.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { chromium } from 'playwright';

const api = 'http://localhost:8100';
const app = 'http://localhost:3100';
const out = process.argv[2];
const emitter = process.env.SKILLS_DOCS_EMITTER;
const python = process.env.SKILL_TRACES_PYTHON;
if (!out || !emitter || !python) throw new Error('Provide OUT_DIR, SKILLS_DOCS_EMITTER and SKILL_TRACES_PYTHON');
fs.mkdirSync(out, { recursive: true });
let headers = {};
const call = async (method, route, body) => {
  const response = await fetch(`${api}${route}`, { method, headers: { ...headers, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(60000) });
  const raw = await response.text();
  let value; try { value = JSON.parse(raw); } catch { value = raw; }
  if (!response.ok) throw new Error(`${method} ${route}: ${response.status} ${String(raw).slice(0, 200)}`);
  return value?.result ?? value;
};
const skills = (method, route, body) => call(method, `/model-hub/skills/${route}`, body);

const email = `maya.chen.${crypto.randomUUID().slice(0, 5)}@northwind.example`;
const password = `Docs-${crypto.randomUUID()}`;
await call('POST', '/accounts/e2e/clean-signup/', { email, password, full_name: 'Maya Chen' });
const tokens = await call('POST', '/accounts/token/', { email, password, remember_me: true });
headers = { Authorization: `Bearer ${tokens.access}` };
const info = await call('GET', '/accounts/user-info/');
headers['X-Organization-Id'] = info.organization.id;
headers['X-Workspace-Id'] = info.default_workspace_id;
const keys = await call('GET', '/accounts/keys/');
const keyPair = keys?.data ?? keys;

const publish = async (name, description, body) => {
  const done = await skills('POST', 'publish/', { files: [{ path: 'SKILL.md', content: `---\nname: ${name}\ndescription: ${description}\n---\n${body}\n` }],
    labels: ['production'], expected_release_revision: 0, acknowledge_warnings: true });
  return { id: done.skill.id, name, version: done.version };
};
const refund = await publish('refund-policy', 'Use when a customer asks about refunds or returns.', '# Refund policy\n\nAsk for the order date. Refund within 30 days.');
const tone = await publish('tone-guide', 'Use when writing any customer reply.', '# Tone guide\n\nBe brief, warm and specific.');
const escalation = await publish('escalation-policy', 'Use when a case needs a human owner.', '# Escalation policy\n\nHand off with the case summary.');
const ctxText = '# Support desk\n\nUse the linked procedures that apply to the request.\n';
const ctx = await skills('POST', 'contexts/', { name: 'support-desk', description: 'Standing instructions for the support assistant.', tags: [], files: [{ path: 'AGENTS.md', content: ctxText }] });
const cid = ctx.context_id;
let draft = await skills('GET', `contexts/${cid}/draft/`);
const deps = { revision: draft.revision, links: [refund, tone, escalation].map((s) => ({ skill_id: s.id, selector: { label: 'production' } })), refresh_skill_ids: [] };
const preview = await skills('POST', `contexts/${cid}/dependencies/preview/`, deps);
await skills('POST', `contexts/${cid}/dependencies/apply/`, { ...deps, expected_fingerprint: preview.fingerprint });
draft = await skills('GET', `contexts/${cid}/draft/`);
const head = await skills('POST', `contexts/${cid}/draft/head-review/`, { revision: draft.revision });
const ack = { revision: draft.revision, expected_digest: head.candidate_digest, expected_head_version: head.expected_head_version, review_fingerprint: head.review_fingerprint };
const saved = await skills('POST', `contexts/${cid}/draft/acknowledge-head/`, ack);
await skills('POST', `contexts/${cid}/draft/publish/`, { ...ack, revision: saved.revision, review_fingerprint: saved.review_fingerprint, base_version: saved.base_version, note: 'First release', acknowledge_warnings: true });
const ctxVersion = await skills('GET', `contexts/${cid}/versions/1/`);
const ctxVersionId = ctxVersion.id ?? ctxVersion.version?.id ?? ctxVersion.version_id;
const grant = (s) => ({ kind: 'skill', resource_id: s.id, labels: ['production'], version_ids: [s.version.id] });
const issued = await skills('POST', 'contexts/credentials/', { purpose: 'consume', binding_ids: [],
  grants: [...[refund, tone, escalation].map(grant), { kind: 'agent_context', resource_id: cid, labels: [], version_ids: [ctxVersionId] }],
  expires_at: new Date(Date.now() + 3600000).toISOString() });

const project = 'support-desk-app';
const agent = (name, resources) => ({ name, skills: resources.map((s) => ({ name: s.name, selector: { version: s.version.number } })), context: { name: 'support-desk', selector: { version: 1 } } });
const emit = (agents, options = {}) => {
  const run = spawnSync(python, ['-I', emitter], { encoding: 'utf8', timeout: 120000, env: { ...process.env, FI_SKILLS_TRACING: 'on' },
    input: JSON.stringify({ credential: issued.secret, project, agents, apiKey: keyPair.api_key, secretKey: keyPair.secret_key, ...options }) });
  if (run.status !== 0) throw new Error(`emitter exited ${run.status}: ${(run.stderr.match(/^([A-Za-z.]+(?:Error|Exception)):/m) ?? [])[1] ?? 'runtime error'}`);
  return JSON.parse(run.stdout.trim().split('\n').at(-1)).trace_id;
};
const traceIds = [];
traceIds.push(emit([agent('refund-agent', [refund, tone])], { requests: 4 }));
traceIds.push(emit([agent('refund-agent', [refund, tone])], { failedRequest: true }));
traceIds.push(emit([agent('billing-agent', [refund])], { requests: 2 }));
try { await skills('DELETE', `contexts/credentials/${issued.id}/`); } catch { /* expires within the hour */ }

const window = () => new URLSearchParams({ from: new Date(Date.now() - 3600000).toISOString(), to: new Date().toISOString(), resource_id: refund.id, group_by: 'version' });
let usage;
for (let attempt = 0; attempt < 60; attempt++) {
  usage = await skills('GET', `usage/?${window()}`);
  if ((usage?.summary?.traces ?? 0) >= 7) break;
  await new Promise((resolve) => setTimeout(resolve, 2000));
}
const projects = await call('GET', '/tracer/project/list_projects/?project_type=observe&page_number=0&page_size=50');
const list = projects?.table ?? projects?.results ?? projects?.data ?? projects?.projects ?? projects;
const projectId = (Array.isArray(list) ? list : []).find((row) => row.name === project)?.id;
if (!projectId) throw new Error(`Observe project not found: ${JSON.stringify(Object.keys(projects ?? {}))}`);
fs.writeFileSync(path.join(out, 'fixture.json'), JSON.stringify({ refund: refund.id, tone: tone.id, escalation: escalation.id, context: cid, projectId,
  usageTraces: usage?.summary?.traces ?? null, traceIds }, null, 2));

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
await context.addInitScript(({ tokens, info }) => {
  localStorage.setItem('accessToken', tokens.access); localStorage.setItem('refreshToken', tokens.refresh); localStorage.setItem('rememberMe', 'true');
  sessionStorage.setItem('organizationId', info.organization.id); sessionStorage.setItem('workspaceId', info.default_workspace_id); sessionStorage.setItem('workspaceOrgId', info.organization.id);
}, { tokens, info });
const page = await context.newPage();
page.setDefaultTimeout(45000);
const results = [];
const settle = async () => {
  await page.waitForFunction(() => document.querySelectorAll('.MuiSkeleton-root').length === 0, undefined, { timeout: 30000 }).catch(() => undefined);
  await page.waitForTimeout(1200);
};
const shot = async (name, steps) => {
  try { await steps(); await settle(); await page.screenshot({ path: path.join(out, `${name}.png`), animations: 'disabled' }); results.push([name, 'ok']); }
  catch (error) { results.push([name, `FAILED ${String(error.message).split('\n')[0]}`]); await page.screenshot({ path: path.join(out, `${name}.FAILED.png`) }).catch(() => undefined); }
};
await shot('skill-runtime', async () => {
  await page.goto(`${app}/dashboard/skills/${refund.id}?tab=runtime`);
  await page.getByText('refund-agent', { exact: true }).first().waitFor();
});
const filter = [{ column_id: 'skill.version_id', filter_config: { col_type: 'SKILL', filter_type: 'text', filter_op: 'equals', filter_value: refund.version.id } }];
await shot('observe-skills-filter', async () => {
  await page.goto(`${app}/dashboard/observe/${projectId}/llm-tracing?tab=traces&observeLinkFilter=${encodeURIComponent(JSON.stringify(filter))}`);
  await page.locator(`.ag-row[row-id="${traceIds[0]}"]:visible`).first().waitFor({ timeout: 60000 });
});
await shot('trace-skills-loaded', async () => {
  await page.locator(`.ag-row[row-id="${traceIds[0]}"]:visible [col-id="trace_name"]`).first().click();
  await page.getByRole('button', { name: /Skills:/ }).click();
  await page.getByRole('list', { name: 'Skills loaded' }).waitFor();
});
await browser.close();
fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
console.log(results.map((row) => row.join(' ')).join('\n'));
if (results.some(([, result]) => result !== 'ok')) process.exitCode = 1;
