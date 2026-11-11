#!/usr/bin/env node
/** Cloud-only, synthetic fixture capture. Never aim at a production deployment. */
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
const origin = process.env.SKILLS_DOCS_API ?? 'http://localhost:8100';
if (new URL(origin).hostname !== 'localhost') throw new Error('Only the isolated localhost E2E stack is permitted');
const out = process.argv[2];
if (!out) throw new Error('Provide an evidence output directory');
fs.mkdirSync(out, { recursive: true });
const prefix = `/model-hub/skills/`;
const contract = JSON.parse(fs.readFileSync(new URL('../public/api/skills-sealed.json', import.meta.url)));
const captures = [];
const pending = [];
let headers = {};
const run = crypto.randomUUID().slice(0, 8);
const routes = Object.entries(contract.paths).flatMap(([route, item]) => Object.keys(item)
  .filter(method => ['get','post','put','patch','delete'].includes(method))
  .map(method => ({ route, method, expression: new RegExp(`^${route.replace(/\{[^}]+\}/g, '[^/]+')}$`) })));
function scrub(value) {
  if (Array.isArray(value)) return value.map(scrub);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [key,
    /^(secret|secret_key|api_key|access|refresh|token|credential)$/i.test(key) ? '[redacted]' : scrub(child)]));
}
async function request(method, route, body, required = false) {
  const idempotencyKey = crypto.randomUUID();
  const response = await fetch(`${origin}${route}`, { method,
    headers: { ...headers, 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(60000) });
  const raw = await response.text();
  let value;
  try { value = JSON.parse(raw); } catch { value = { non_json: true, bytes: Buffer.byteLength(raw) }; }
  if (route.startsWith(prefix)) {
    const pathname = route.split('?')[0];
    const matched = routes.filter(r => r.method === method.toLowerCase() && r.expression.test(pathname))
      .sort((a,b) => (a.route.match(/\{/g)?.length ?? 0) - (b.route.match(/\{/g)?.length ?? 0))[0];
    captures.push({ method, path: route, contract_path: matched?.route ?? null,
      request: { ...(body === undefined ? {} : { body: scrub(body) }), idempotency_key: idempotencyKey,
        authentication: headers.Authorization?.startsWith('Context ') ? 'Context (credential omitted)' : 'Bearer (token omitted)',
        ...(headers['X-Context-Resolution'] ? { resolution_header: headers['X-Context-Resolution'] } : {}) },
      status: response.status, response: scrub(value) });
    console.log(`${method} ${matched?.route ?? pathname} ${response.status}`);
    fs.writeFileSync(path.join(out, 'http-examples.json'), JSON.stringify({
      product_commit: contract.provenance.product_commit, synthetic: true, transport: 'real HTTP; Skills provider and GitHub transport fakes in E2E stack', captures,
    }, null, 2));
  }
  if (required && !response.ok) throw new Error(`${method} ${route}: ${response.status} ${JSON.stringify(value).slice(0,500)}`);
  return value?.result ?? value;
}
const get = (route, required=false) => request('GET', prefix+route, undefined, required);
const post = (route, body, required=false) => request('POST', prefix+route, body, required);
const put = (route, body, required=false) => request('PUT', prefix+route, body, required);
try {
  const email = `docs-${run}@example.invalid`;
  const password = `Docs-${crypto.randomUUID()}`;
  await request('POST', '/accounts/e2e/clean-signup/', { email, password, full_name: 'Synthetic documentation operator' }, true);
  const tokens = await request('POST', '/accounts/token/', {email,password,remember_me:true}, true);
  headers = { Authorization: `Bearer ${tokens.access}` };
  const info = await request('GET', '/accounts/user-info/', undefined, true);
  headers['X-Organization-Id'] = info.organization.id;
  headers['X-Workspace-Id'] = info.default_workspace_id;
  for (const route of ['contexts/capabilities/','testing-options/','templates/','spend-policy/','review-inbox/','contexts/credentials/','contexts/campaigns/']) await get(route);
  const name = `docs-policy-${run}`;
  const files = [{ path:'SKILL.md',content:`---\nname: ${name}\ndescription: Use when reviewing the synthetic documentation policy.\n---\nRequire an observed tool result before claiming completion.\n` }];
  await post('checks/', { files });
  const leaf = await post('publish/', { files, labels:['production'],expected_release_revision:0,acknowledge_warnings:true }, true);
  const sid = leaf.skill.id;
  for (const route of ['',`${sid}/`,`${sid}/versions/`,`${sid}/versions/1/`,`${sid}/labels/`,`${sid}/labels/history/`,`${sid}/label-protection/`,`${sid}/label-protection/history/`,`${sid}/usage/`,`${sid}/adoption/`,`${sid}/context-dependents/`,`${sid}/source/`,`${sid}/test-evidence/`,`${sid}/tests/`,`${sid}/test-runs/`,`${sid}/versions/1/migration-export/`,`${sid}/versions/1/inspection/`,`resolve/?name=${name}&version=1`]) await get(route);
  const ctxName = `docs-context-${run}`;
  const ownedFiles = [{path:'AGENTS.md',content:'# Synthetic support context\nConsult the accepted policy skill before answering.\n'}];
  let draft = await post('contexts/', {name:ctxName,description:'Synthetic documentation context',tags:['docs'],files:ownedFiles},true);
  const cid = draft.context_id;
  assert.ok(cid);
  await get('contexts/');
  await get(`contexts/${cid}/`);
  draft = await get(`contexts/${cid}/draft/`,true);
  await get(`contexts/${cid}/draft/files/?path=AGENTS.md&revision=${draft.revision}`);
  draft = await put(`contexts/${cid}/draft/`, {revision:draft.revision,base_version:draft.base_version,files:ownedFiles,description:'Synthetic documentation context',note:'Reviewed root'}, true);
  const input = { revision:draft.revision, links:[{skill_id:sid,selector:{label:'production'}}], refresh_skill_ids:[] };
  const preview = await post(`contexts/${cid}/dependencies/preview/`,input,true);
  await post(`contexts/${cid}/dependencies/apply/`,{...input,expected_fingerprint:preview.fingerprint},true);
  await get(`${sid}/context-dependents/`);
  draft = await get(`contexts/${cid}/draft/`,true);
  await get(`contexts/${cid}/draft/checkpoints/`);
  const head = await post(`contexts/${cid}/draft/head-review/`,{revision:draft.revision},true);
  const ack = {revision:draft.revision,expected_digest:head.candidate_digest,expected_head_version:head.expected_head_version,review_fingerprint:head.review_fingerprint};
  const saved = await post(`contexts/${cid}/draft/acknowledge-head/`,ack,true);
  const published = await post(`contexts/${cid}/draft/publish/`,{...ack,revision:saved.revision,review_fingerprint:saved.review_fingerprint,base_version:saved.base_version,note:'Synthetic documentation release',acknowledge_warnings:true},true);
  for (const route of [`contexts/${cid}/versions/`,`contexts/${cid}/versions/1/`,`contexts/${cid}/versions/1/inspection/`,`contexts/${cid}/versions/1/inspection/files/?path=AGENTS.md`,`contexts/${cid}/release-state/`,`contexts/${cid}/consumers/`,`contexts/${cid}/bindings/`,`contexts/${cid}/test-runs/`,`contexts/resolve/?name=${ctxName}&version=1`,`consumption/resolve/?name=${name}&version=1`,`contexts/${cid}/versions/1/manifest/`,`contexts/${cid}/versions/1/files/?path=AGENTS.md`]) await get(route);
  await post(`contexts/${cid}/versions/1/access-check/`,{});
  await post(`contexts/${cid}/draft/start/`,{revision:0,from_version:1});
  draft = await get(`contexts/${cid}/draft/`,true);
  const review = await post(`contexts/${cid}/draft/head-review/`,{revision:draft.revision},true);
  const checkpoint = await post(`contexts/${cid}/draft/checkpoints/`,{revision:draft.revision,expected_digest:draft.recovery_digest,reason:'manual',suspend:false},true);
  await get(`contexts/${cid}/draft/checkpoints/`);
  await post(`contexts/${cid}/draft/checkpoints/${checkpoint.checkpoint.id}/restore/`,{revision:draft.revision,expected_digest:draft.recovery_digest},true);
  draft = await get(`contexts/${cid}/draft/`,true);
  await post(`contexts/${cid}/release/review/`,{operation:'publish',revision:draft.revision});
  await get(`${sid}/test-evidence/?candidate=version&version=1`);
  const suite = await get(`${sid}/tests/`);
  await put(`${sid}/tests/`,{revision:suite.revision,cases:[]});
  await request('PATCH',prefix+`${sid}/`,{tags:['documentation']});
  const bindingInput = {name:'Synthetic documentation binding',kind:'repository',selector:{version:1},update_mode:'repository_lock',profile:'codex',profile_version:'unqualified-docs-fixture',repository:{provider:'github',repository_id:`synthetic/docs-${run}`,default_branch:'main',project_scope:''},expected_report_interval_seconds:3600};
  let binding = await post(`contexts/${cid}/bindings/`,bindingInput,true);
  if (binding.id) binding = await request('PATCH',prefix+`contexts/bindings/${binding.id}/`,{revision:binding.revision,binding:{...bindingInput,name:'Reviewed synthetic documentation binding'}},true);
  const humanHeaders = {...headers};
  const contextVersion = await get(`contexts/${cid}/versions/1/`,true);
  const leafVersion = await get(`${sid}/versions/1/`,true);
  const credential = await post('contexts/credentials/',{purpose:'consume',grants:[{kind:'agent_context',resource_id:cid,labels:[],version_ids:[contextVersion.id]},{kind:'skill',resource_id:sid,labels:[],version_ids:[leafVersion.id]}],binding_ids:[],expires_at:new Date(Date.now()+3600000).toISOString()},true);
  try {
    headers={Authorization:`Context ${credential.secret}`};
    const resolution=await get(`contexts/resolve/?name=${ctxName}&version=1`,true);
    headers['X-Context-Resolution']=resolution.resolution_id;
    await get(`contexts/${cid}/versions/1/manifest/`,true);
    await get(`contexts/${cid}/versions/1/files/?path=AGENTS.md`,true);
    await post(`contexts/${cid}/versions/1/access-check/`,{},true);
    delete headers['X-Context-Resolution'];
    const leafResolution=await get(`consumption/resolve/?name=${name}&version=1`,true);
    headers['X-Context-Resolution']=leafResolution.resolution_id;
    await get(`consumption/${sid}/versions/1/manifest/`,true);
    await get(`consumption/${sid}/versions/1/files/?path=SKILL.md`,true);
    await post(`consumption/${sid}/versions/1/access-check/`,{},true);
  } finally {
    headers=humanHeaders;
    await request('DELETE',prefix+`contexts/credentials/${credential.id}/`,undefined,true);
  }
  if (binding.id) await request('DELETE',prefix+`contexts/bindings/${binding.id}/`,{revision:binding.revision},true);
  const release = await post('release-requests/preview/',{resource_id:sid,kind:'skill',candidate_version_id:leafVersion.id,label:'staging',target:null,evidence:[],external_pipeline:null});
  assert.ok(release.packet);
  await post(`${sid}/versions/1/restore/`,{note:'Explicit synthetic restoration, not promotion'});
  await get(`${sid}/compare/?from=1&to=2`);
  fs.writeFileSync(path.join(out,'fixture-state.json'),JSON.stringify({sid,cid,published},null,2));
  // Capture missing UI subjects in the VM browser; never persist authentication.
  const { chromium } = await import('playwright');
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:900}});
  await context.addInitScript(({tokens,info}) => {
    localStorage.setItem('accessToken',tokens.access);localStorage.setItem('refreshToken',tokens.refresh);localStorage.setItem('rememberMe','true');
    sessionStorage.setItem('organizationId',info.organization.id);sessionStorage.setItem('workspaceId',info.default_workspace_id);sessionStorage.setItem('workspaceOrgId',info.organization.id);
  },{tokens,info});
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  fs.mkdirSync(path.join(out,'shots'),{recursive:true});
  await page.goto('http://localhost:3100/dashboard/skills');
  await page.getByRole('button',{name:/^(Import|Import a folder or ZIP)$/}).click();
  await page.getByRole('tab',{name:'GitHub',exact:true}).click();
  await page.getByRole('textbox',{name:'Public repository URL',exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'shots','github-import.png')});
  await page.goto(`http://localhost:3100/dashboard/skills/contexts/${cid}?version=1`);
  await page.getByRole('button',{name:'Edit viewed v1',exact:true}).waitFor();
  await page.screenshot({path:path.join(out,'shots','context-detail.png')});
  await page.getByRole('tab',{name:'Use',exact:true}).click();
  await page.screenshot({path:path.join(out,'shots','context-use.png')});
  await browser.close();
} catch (error) {
  pending.push(String(error));
  process.exitCode=1;
} finally {
  const success = new Set(captures.filter(row=>row.status>=200&&row.status<300).map(row=>`${row.method} ${row.contract_path}`));
  const report = { operations:routes.length, observed_success:success.size, successful_operations:[...success].sort(),
    unverified:routes.filter(row=>!success.has(`${row.method.toUpperCase()} ${row.route}`)).map(row=>`${row.method.toUpperCase()} ${row.route}`), errors:pending };
  fs.writeFileSync(path.join(out,'coverage.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({operations:report.operations,observed_success:report.observed_success,errors:pending}));
}
