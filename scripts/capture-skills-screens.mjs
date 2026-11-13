#!/usr/bin/env node
/**
 * Cloud-only capture of the Skills product screens at 1440x900 for the documentation.
 * Run on the VM against the isolated localhost E2E stack. It builds a synthetic customer-like
 * workspace with neutral names so no internal fixture identifier appears in an image.
 *   SKILLS_DOCS_API=http://localhost:8100 SKILLS_DOCS_APP=http://localhost:3100 node scripts/capture-skills-screens.mjs OUT_DIR [only,names]
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { chromium } from 'playwright';

const api = process.env.SKILLS_DOCS_API ?? 'http://localhost:8100';
const app = process.env.SKILLS_DOCS_APP ?? 'http://localhost:3100';
for (const origin of [api, app]) if (new URL(origin).hostname !== 'localhost') throw new Error('Only the isolated localhost stack is permitted');
const out = process.argv[2];
const only = process.argv[3]?.split(',');
if (!out) throw new Error('Provide an output directory');
fs.mkdirSync(out, { recursive: true });
const prefix = '/model-hub/skills/';
let headers = {};
const call = async (method, route, body, extra = {}) => {
  const response = await fetch(`${api}${route}`, { method, headers: { ...headers, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID(), ...extra },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(60000) });
  const raw = await response.text();
  let value; try { value = JSON.parse(raw); } catch { value = raw; }
  if (!response.ok) throw new Error(`${method} ${route}: ${response.status} ${raw.slice(0, 300)}`);
  return value?.result ?? value;
};
const get = (r) => call('GET', prefix + r);
const post = (r, b, e) => call('POST', prefix + r, b, e);
const put = (r, b) => call('PUT', prefix + r, b);


const crcTable = new Int32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c; });
const crc32 = (buf) => { let c = -1; for (const byte of buf) c = crcTable[(c ^ byte) & 255] ^ (c >>> 8); return (c ^ -1) >>> 0; };
const zip = (entries) => { // stored (uncompressed) ZIP, enough for the import preview
  const parts = []; const central = []; let offset = 0;
  for (const [name, text] of Object.entries(entries)) {
    const data = Buffer.from(text); const nameBytes = Buffer.from(name); const crc = crc32(data);
    const local = Buffer.alloc(30); local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22); local.writeUInt16LE(nameBytes.length, 26);
    parts.push(local, nameBytes, data);
    const entry = Buffer.alloc(46); entry.writeUInt32LE(0x02014b50, 0); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt32LE(crc, 16); entry.writeUInt32LE(data.length, 20); entry.writeUInt32LE(data.length, 24); entry.writeUInt16LE(nameBytes.length, 28); entry.writeUInt32LE(offset, 42);
    central.push(entry, nameBytes); offset += 30 + nameBytes.length + data.length;
  }
  const centralBuf = Buffer.concat(central); const end = Buffer.alloc(22); end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(Object.keys(entries).length, 8); end.writeUInt16LE(Object.keys(entries).length, 10); end.writeUInt32LE(centralBuf.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...parts, centralBuf, end]);
};

const email = `maya.chen.${crypto.randomUUID().slice(0, 5)}@northwind.example`;
const password = `Docs-${crypto.randomUUID()}`;
await call('POST', '/accounts/e2e/clean-signup/', { email, password, full_name: 'Maya Chen' });
const tokens = await call('POST', '/accounts/token/', { email, password, remember_me: true });
headers = { Authorization: `Bearer ${tokens.access}` };
const info = await call('GET', '/accounts/user-info/');
headers['X-Organization-Id'] = info.organization.id;
headers['X-Workspace-Id'] = info.default_workspace_id;

const skillFile = (name, description, body) => [{ path: 'SKILL.md', content: `---\nname: ${name}\ndescription: ${description}\n---\n${body}\n` }];
const publishLeaf = async (name, description, bodies, labels = []) => {
  let id; let number = 0;
  for (const body of bodies) {
    const files = skillFile(name, description, body);
    const done = await post(number === 0 ? 'publish/' : `${id}/versions/`, number === 0
      ? { files, labels: [], expected_release_revision: 0, acknowledge_warnings: true }
      : { files, base_version: number, note: 'Tighten wording', labels: [], acknowledge_warnings: true, force: false });
    void 0;
    id = done.skill?.id ?? id; number = done.version.number;
  }
  for (const [label, version] of labels) {
    const state = await get(`${id}/labels/`).catch(() => null);
    const revision = (await get(`${id}/`).catch(() => ({}))).release_revision ?? 0;
    await put(`${id}/labels/${label}/`, { version, expected_version: null, note: 'Reviewed release', expected_release_revision: revision }).catch((error) => console.error('label', label, String(error.message).slice(0, 160)));
  }
  return { id, name, number };
};
const refund = await publishLeaf('refund-policy', 'Use when a customer asks about refunds, returns, or support-policy exceptions.', [
  '# Refund policy\n\nAsk for the order date and the reason. Refund within 30 days.',
  '# Refund policy\n\nAsk for the order date and the reason. Refund within 30 days. Escalate anything over $100.',
  '# Refund policy\n\nAsk for the order date and the reason. Refund within 30 days. Escalate anything over $100 and never promise an unapproved refund.',
], [['production', 3], ['staging', 2]]);
const chargeback = await publishLeaf('chargeback-policy', 'Use when a customer disputes a card transaction.', ['# Chargeback policy\n\nCollect the transaction id and the dispute reason before replying.'], [['production', 1]]);
const shipping = await publishLeaf('shipping-policy', 'Use when a customer asks where an order is.', ['# Shipping policy\n\nLook up the carrier status. Quote the carrier, not an estimate.'], [['production', 1]]);
const ctxFiles = [{ path: 'AGENTS.md', content: '# Support desk\n\nUse the refund procedure for refund questions.\nUse the chargeback procedure for disputed card transactions.\nDo not claim an external action succeeded without its tool result.\n' }];
const ctx = await post('contexts/', { name: 'support-desk', description: 'Standing instructions for the customer support assistant.', tags: [], files: ctxFiles });
const cid = ctx.context_id;
let draft = await get(`contexts/${cid}/draft/`);
const links = [refund, chargeback, shipping].map((s) => ({ skill_id: s.id, selector: { version: 1 } }));
const input = { revision: draft.revision, links, refresh_skill_ids: [] };
const preview = await post(`contexts/${cid}/dependencies/preview/`, input);
await post(`contexts/${cid}/dependencies/apply/`, { ...input, expected_fingerprint: preview.fingerprint });
draft = await get(`contexts/${cid}/draft/`);
const head = await post(`contexts/${cid}/draft/head-review/`, { revision: draft.revision });
const ack = { revision: draft.revision, expected_digest: head.candidate_digest, expected_head_version: head.expected_head_version, review_fingerprint: head.review_fingerprint };
const saved = await post(`contexts/${cid}/draft/acknowledge-head/`, ack);
await post(`contexts/${cid}/draft/publish/`, { ...ack, revision: saved.revision, review_fingerprint: saved.review_fingerprint, base_version: saved.base_version, note: 'First release', acknowledge_warnings: true });
// A second skill version so a follower has an update available.
await post(`${chargeback.id}/versions/`, { files: skillFile('chargeback-policy', 'Use when a customer disputes a card transaction.', '# Chargeback policy\n\nCollect the transaction id and the dispute reason before replying. Offer the dispute form.'), base_version: 1, note: 'Add dispute form', labels: [], acknowledge_warnings: true, force: false });

// A second context follows chargeback-policy:production; upstream then advances so an update is offered.
const rev = async (id) => (await get(`${id}/`)).release_revision ?? 0;
await put(`${chargeback.id}/labels/production/`, { version: 1, expected_version: null, note: 'Reviewed release', expected_release_revision: await rev(chargeback.id) }).catch(() => undefined);
const returns = await post('contexts/', { name: 'returns-desk', description: 'Standing instructions for the returns assistant.', tags: [], files: [{ path: 'AGENTS.md', content: '# Returns desk\n\nHandle returns and chargebacks using the linked procedures.\n' }] });
{
  let d = await get(`contexts/${returns.context_id}/draft/`);
  const inp = { revision: d.revision, links: [{ skill_id: chargeback.id, selector: { label: 'production' } }, { skill_id: refund.id, selector: { label: 'production' } }], refresh_skill_ids: [] };
  const pv = await post(`contexts/${returns.context_id}/dependencies/preview/`, inp);
  await post(`contexts/${returns.context_id}/dependencies/apply/`, { ...inp, expected_fingerprint: pv.fingerprint });
  d = await get(`contexts/${returns.context_id}/draft/`);
  const h = await post(`contexts/${returns.context_id}/draft/head-review/`, { revision: d.revision });
  const a = { revision: d.revision, expected_digest: h.candidate_digest, expected_head_version: h.expected_head_version, review_fingerprint: h.review_fingerprint };
  const sv = await post(`contexts/${returns.context_id}/draft/acknowledge-head/`, a);
  await post(`contexts/${returns.context_id}/draft/publish/`, { ...a, revision: sv.revision, review_fingerprint: sv.review_fingerprint, base_version: sv.base_version, note: 'First release', acknowledge_warnings: true });
}
await put(`${chargeback.id}/labels/production/`, { version: 2, expected_version: 1, note: 'Add dispute form', expected_release_revision: await rev(chargeback.id) }).catch((e) => console.error('move', String(e.message).slice(0, 200)));
// A second release of support-desk so v1 is a historical release.
{
  const started = await post(`contexts/${cid}/draft/start/`, { revision: 0, from_version: 1 });
  let d = await get(`contexts/${cid}/draft/`);
  d = await put(`contexts/${cid}/draft/`, { revision: d.revision, base_version: 1, files: [{ path: 'AGENTS.md', content: '# Support desk\n\nUse the refund procedure for refund questions.\nUse the chargeback procedure for disputed card transactions.\nAsk for the order number first.\nDo not claim an external action succeeded without its tool result.\n' }], description: 'Standing instructions for the customer support assistant.', note: 'Ask for the order number' });
  const h = await post(`contexts/${cid}/draft/head-review/`, { revision: d.revision });
  const a = { revision: d.revision, expected_digest: h.candidate_digest, expected_head_version: h.expected_head_version, review_fingerprint: h.review_fingerprint };
  const sv = await post(`contexts/${cid}/draft/acknowledge-head/`, a);
  await post(`contexts/${cid}/draft/publish/`, { ...a, revision: sv.revision, review_fingerprint: sv.review_fingerprint, base_version: sv.base_version, note: 'Ask for the order number', acknowledge_warnings: true });
}
// Some fetches so the usage view has data.
for (let i = 0; i < 4; i++) { await get(`resolve/?name=refund-policy&version=${1 + (i % 3)}`).catch(() => undefined); await get(`${refund.id}/versions/${1 + (i % 3)}/files/?path=SKILL.md`).catch(() => undefined); }
await get('download/?names=refund-policy&label=production').catch(() => undefined);
fs.writeFileSync(path.join(out, 'fixture.json'), JSON.stringify({ refund, chargeback, shipping, cid, returns: returns.context_id }, null, 2));


const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
await context.addInitScript(({ tokens, info }) => {
  localStorage.setItem('accessToken', tokens.access); localStorage.setItem('refreshToken', tokens.refresh); localStorage.setItem('rememberMe', 'true');
  sessionStorage.setItem('organizationId', info.organization.id); sessionStorage.setItem('workspaceId', info.default_workspace_id); sessionStorage.setItem('workspaceOrgId', info.organization.id);
}, { tokens, info });
const page = await context.newPage();
page.setDefaultTimeout(30000);
const results = [];
const shot = async (name, steps) => {
  if (only && !only.includes(name)) return;
  try { await steps(); await page.waitForTimeout(600); await page.screenshot({ path: path.join(out, `${name}.png`) }); results.push([name, 'ok']); }
  catch (error) { results.push([name, `FAILED ${String(error.message).split('\n')[0]}`]); try { await page.screenshot({ path: path.join(out, `${name}.FAILED.png`) }); } catch {} }
};
const go = async (route) => { await page.goto(`${app}${route}`); await page.waitForLoadState('networkidle').catch(() => undefined); };

const hostFix = async () => { await page.evaluate(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); for (let n = w.nextNode(); n; n = w.nextNode()) n.nodeValue = n.nodeValue.replaceAll('http://localhost:8100', 'https://api.futureagi.com'); }); };
const ctxUrl = (id, version = 1) => `/dashboard/skills/contexts/${id}?version=${version}`;
const importZip = async (name, entries) => {
  await go('/dashboard/skills');
  await page.getByRole('button', { name: /^(Import|Import a folder or ZIP)$/ }).click();
  await page.getByLabel(/files|ZIP|folder/i).first().setInputFiles({ name, mimeType: 'application/zip', buffer: zip(entries) }).catch(async () => { await page.locator('input[type=file]').first().setInputFiles({ name, mimeType: 'application/zip', buffer: zip(entries) }); });
};
const skillText = (name, description, body) => `---\nname: ${name}\ndescription: ${description}\n---\n${body}\n`;
const importEntries = {
  'escalation-policy/SKILL.md': skillText('escalation-policy', 'Use when a case needs a human owner or a manager decision.', '# Escalation policy\n\nHand off with the case summary.'),
  'shipping-policy/SKILL.md': skillText('shipping-policy', 'Use when a customer asks where an order is.', '# Shipping policy\n\nLook up the carrier status. Quote the carrier, not an estimate.'),
  'refund-policy/SKILL.md': skillText('refund-policy', 'Use when a customer asks about refunds, returns, or support-policy exceptions.', '# Refund policy\n\nRefund within 14 days.'),
  'broken-policy/SKILL.md': '---\nname: broken-policy\n---\n# Missing description\n',
};
await shot('skills-library', async () => { await go('/dashboard/skills'); await page.getByText('refund-policy').first().waitFor(); });
// Quickstart path, driven through the UI so every state is real: create, edit, publish with a label, use.
const quickName = 'support-policy';
await shot('skills-create', async () => {
  await go('/dashboard/skills');
  await page.getByRole('button', { name: 'New skill', exact: true }).click();
  await page.getByRole('textbox', { name: /^Name/ }).fill(quickName);
  await page.getByRole('textbox', { name: /^Description/ }).fill("Use when answering refund or return questions using the team's reviewed support policy.");
  await page.getByRole('combobox', { name: 'Start from' }).click();
  await page.getByRole('option', { name: 'Support policy' }).click();
});
let quickId;
await shot('skills-editor-checks', async () => {
  await page.getByRole('button', { name: 'Create skill', exact: true }).click();
  await page.getByRole('button', { name: 'Open editor', exact: true }).click();
  await page.waitForURL(/\/dashboard\/skills\/[0-9a-f-]+\/edit/);
  quickId = page.url().match(/skills\/([0-9a-f-]{36})/)[1];
  await page.getByText('Saved', { exact: true }).first().waitFor();
  await page.waitForTimeout(6500);
});
await shot('skills-publish', async () => {
  await page.getByRole('button', { name: 'Publish', exact: true }).click();
  await page.getByText(/After publishing, move label/).first().waitFor();
  await page.getByRole('checkbox', { name: 'production' }).check();
  const note = page.getByRole('textbox', { name: /note/i }).first();
  await note.fill('Initial reviewed support policy').catch(() => undefined);
  await page.locator('[role=dialog] *').evaluateAll((els) => els.forEach((e) => { if (e.scrollHeight > e.clientHeight + 4) e.scrollTop = e.scrollHeight; }));
});
await shot('skills-use-claude-code', async () => {
  await page.getByRole('button', { name: 'Publish', exact: true }).last().click();
  await page.waitForTimeout(3000);
  await go(`/dashboard/skills/${quickId}`);
  await page.getByRole('tab', { name: 'Use', exact: true }).click();
  await page.getByRole('combobox', { name: /Use label or version/ }).click().catch(() => undefined);
  await page.getByRole('option', { name: /production/ }).click().catch(() => undefined);
  await page.waitForTimeout(1000);
  await hostFix();
});
await shot('skills-files', async () => { await go(`/dashboard/skills/${refund.id}`); });
await shot('skills-compare', async () => { await go(`/dashboard/skills/${refund.id}/compare?from=1&to=3`); });
await shot('skills-versions', async () => { await go(`/dashboard/skills/${refund.id}`); await page.getByRole('tab', { name: 'Versions', exact: true }).click(); });
await shot('skills-move-label', async () => {
  await go(`/dashboard/skills/${refund.id}`); await page.getByRole('tab', { name: 'Versions', exact: true }).click();
  await page.getByText('Move', { exact: true }).nth(1).click(); await page.waitForTimeout(3000);
});
await shot('skills-label-history', async () => {
  await go(`/dashboard/skills/${refund.id}`); await page.getByRole('tab', { name: 'Versions', exact: true }).click();
  await page.getByRole('button', { name: 'Label history', exact: true }).click();
});
await shot('skills-usage', async () => { await go(`/dashboard/skills/${refund.id}`); await page.getByRole('tab', { name: 'Usage', exact: true }).click(); await page.waitForTimeout(1500); });
await shot('skills-use-clients', async () => {
  await go(`/dashboard/skills/${refund.id}`); await page.getByRole('tab', { name: 'Use', exact: true }).click();
  await hostFix();
  await page.getByRole('combobox', { name: 'Coding client' }).click();
});
await shot('github-import', async () => {
  await go('/dashboard/skills');
  await page.getByRole('button', { name: /^(Import|Import a folder or ZIP)$/ }).click();
  await page.getByRole('tab', { name: 'GitHub', exact: true }).click();
  await page.getByRole('textbox', { name: 'Public repository URL', exact: true }).waitFor();
});
await shot('skills-dependents', async () => { await go(`/dashboard/skills/${chargeback.id}`); await page.getByRole('tab', { name: 'Dependents', exact: true }).click(); await page.waitForTimeout(1500); });
await shot('skills-context-library', async () => { await go('/dashboard/skills/contexts'); await page.getByText('support-desk').first().waitFor(); });
await shot('context-detail', async () => { await go(ctxUrl(cid, 1)); await page.getByRole('button', { name: /Edit viewed v1/ }).waitFor(); });
await shot('context-linked-skills', async () => { await go(ctxUrl(cid, 1)); await page.getByRole('tab', { name: 'Linked skills', exact: true }).click(); });
await shot('context-accepted-lock', async () => { await go(ctxUrl(returns.context_id, 1)); await page.getByRole('tab', { name: 'Linked skills', exact: true }).click(); await page.waitForTimeout(1500); });
await shot('context-historical-editor', async () => { await go(ctxUrl(cid, 1)); await page.getByRole('button', { name: /Edit viewed v1/ }).click(); await page.getByRole('button', { name: 'Start selected draft', exact: true }).waitFor(); });
await shot('context-versions', async () => { await go(ctxUrl(cid, 2)); await page.getByRole('tab', { name: 'Versions', exact: true }).click(); await page.waitForTimeout(1500); });
await shot('context-tests', async () => { await go(ctxUrl(cid, 2)); await page.getByRole('tab', { name: 'Tests', exact: true }).click(); await page.waitForTimeout(1500); });
await shot('context-consumers', async () => { await go(ctxUrl(cid, 2)); await page.getByRole('tab', { name: 'Consumers', exact: true }).click(); await page.waitForTimeout(1500); });
await shot('context-recovery', async () => { await go(ctxUrl(cid, 2)); await page.getByRole('tab', { name: 'Recovery', exact: true }).click(); await page.waitForTimeout(6000); });
await shot('context-use', async () => { await go(ctxUrl(cid, 1)); await page.getByRole('tab', { name: 'Use', exact: true }).click(); });
await shot('campaign-boundary', async () => { await go('/dashboard/skills/contexts/rollouts'); });
await shot('skills-reviews', async () => { await go('/dashboard/skills/reviews'); await page.waitForTimeout(1500); });
await shot('skills-allowance', async () => { await go('/dashboard/skills/allowance'); await page.waitForTimeout(1500); });
await shot('context-historical-draft', async () => { await go(ctxUrl(cid, 1)); await page.getByRole('button', { name: /Edit viewed v1/ }).click(); await page.getByRole('button', { name: 'Start selected draft', exact: true }).click(); await page.waitForTimeout(3000); });
await shot('context-draft-review', async () => { await go(`/dashboard/skills/contexts/${cid}/review`); await page.waitForTimeout(3000); });
await shot('skills-import-preview', async () => {
  await importZip('team-skills.zip', importEntries);
  await page.getByRole('button', { name: 'Preview import', exact: true }).click();
  await page.getByText('escalation-policy').first().waitFor();
});
await shot('skills-import-result', async () => {
  await importZip('team-skills.zip', importEntries);
  await page.getByRole('button', { name: 'Preview import', exact: true }).click();
  await page.getByText('escalation-policy').first().waitFor();
  await page.getByRole('button', { name: /^Import( \d+)?$/ }).last().click();
  await page.waitForTimeout(2500);
});
await browser.close();
fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
console.log(results.map((r) => r.join(' ')).join('\n'));
