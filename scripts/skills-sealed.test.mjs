import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const contract = JSON.parse(read('public/api/skills-sealed.json'));
const pages = fs.readdirSync(path.join(root,'src/pages/docs/skills')).filter(f=>f.endsWith('.mdx'));

test('Skills API subset is pinned and has no dangling schema references', () => {
  assert.equal(contract.provenance.product_commit,'cb00e2f29d7bbce14b861d021542cf3bf989a237');
  assert.equal(contract.provenance.sha256,'de2ead8fb5a73cdc6e263f5f255e36da4a47a94456fa693cc2207f0b47f00250');
  assert.equal(Object.keys(contract.paths).length,152);
  assert.equal(Object.keys(contract.definitions).length,534);
  const methods=new Set(['get','post','put','patch','delete','head','options']);
  assert.equal(Object.values(contract.paths).reduce((count,item)=>count+Object.keys(item).filter(method=>methods.has(method)).length,0),182);
  function visit(value) {
    if (!value || typeof value!=='object') return;
    if (value.$ref) assert.ok(contract.definitions[value.$ref.replace('#/definitions/','')],value.$ref);
    for (const child of Object.values(value)) visit(child);
  }
  visit(contract);
});

test('every current Skills operation is retained without rewriting its contract', () => {
  assert.ok(process.env.SKILLS_SOURCE_SWAGGER,'Set SKILLS_SOURCE_SWAGGER to the pinned product Swagger file');
  const sourceBytes=fs.readFileSync(process.env.SKILLS_SOURCE_SWAGGER);
  assert.equal(createHash('sha256').update(sourceBytes).digest('hex'),contract.provenance.sha256);
  const source=JSON.parse(sourceBytes);
  for (const field of ['basePath','consumes','produces','securityDefinitions','security']) assert.deepEqual(contract[field],source[field],field);
  // Same route selection as scripts/generate-skills-reference.mjs.
  const paths=Object.fromEntries(Object.entries(source.paths).filter(([route])=>route.startsWith('/model-hub/skills/')||route==='/tracer/trace/skill-projection/'));
  assert.deepEqual(contract.paths,paths);
  for (const [name,schema] of Object.entries(contract.definitions)) assert.deepEqual(schema,source.definitions[name],name);
});

test('current contract and screenshot provenance are disclosed without relabeling historical captures', () => {
  const overview=read('src/pages/docs/skills/index.mdx');
  const reference=read('src/pages/docs/skills/sealed-api.mdx');
  for (const text of [overview,reference]) {
    assert.ok(text.includes(contract.provenance.product_commit));
    assert.ok(text.includes('e503da41fd21655c94b7d46e64d202c44a886a47'));
  }
  const guide=read('src/pages/docs/skills/api-reference.mdx');
  for (const [method,route] of [
    ['get','/model-hub/skills/archived/'],
    ['get','/model-hub/skills/archived/{resource_id}/restore-review/'],
    ['post','/model-hub/skills/archived/{resource_id}/restore/'],
    // Lean runtime reads and the trace projection the Runtime views use.
    ['get','/model-hub/skills/usage/'],
    ['get','/model-hub/skills/comparison/'],
    ['get','/model-hub/skills/loads/'],
    ['get','/model-hub/skills/filter-values/'],
    ['post','/tracer/trace/skill-projection/'],
  ]) {
    assert.ok(contract.paths[route]?.[method],route);
    assert.ok(guide.includes(`${method.toUpperCase()} ${route}`),route);
  }
  assert.match(guide,/included in the \[refreshed generated contract\]/);
});

test('every Skills page is reachable from navigation', () => {
  const nav=read('src/lib/navigation.ts');
  for (const page of pages) {
    const route=page==='index.mdx'?'/docs/skills':`/docs/skills/${page.replace('.mdx','')}`;
    assert.ok(nav.includes(`'${route}'`),route);
  }
});

test('Skills page links and screenshots exist', () => {
  for (const page of pages) {
    const text=read(`src/pages/docs/skills/${page}`);
    for (const [,route] of text.matchAll(/\]\((\/docs\/skills[^)#]*)/g)) {
      const leaf=route.replace('/docs/skills','').replace(/^\//,'') || 'index';
      assert.ok(fs.existsSync(path.join(root,`src/pages/docs/skills/${leaf}.mdx`)),`${page}: ${route}`);
    }
    for (const [,image] of text.matchAll(/!\[[^\]]*\]\((\/images\/[^)]+)\)/g)) {
      assert.ok(fs.existsSync(path.join(root,'public',image)),`${page}: ${image}`);
    }
  }
});

test('new product captures retain the requested 1440 by 900 viewport', () => {
  for (const name of ['context-linked-skills','context-tests','context-recovery','rollback-review','release-renewal','target-registration','context-accepted-lock','exact-release-review','durable-release-receipt','context-historical-editor','campaign-boundary','retained-migration','github-import','context-detail','context-use']) {
    const bytes=fs.readFileSync(path.join(root,`public/images/docs/skills/${name}.png`));
    assert.equal(bytes.readUInt32BE(16),1440,name);
    assert.equal(bytes.readUInt32BE(20),900,name);
  }
});

test('every referenced UI capture matches the refreshed source manifest', () => {
  const manifest=JSON.parse(read('public/images/docs/skills/capture-manifest.json'));
  assert.equal(manifest.product_commit,contract.provenance.product_commit);
  assert.equal(manifest.synthetic,true);
  assert.equal(manifest.images.length,36);
  // Every image is recaptured at the contract head except explicitly retained, labeled earlier captures.
  const retained=manifest.images.filter(image=>image.product_commit!==contract.provenance.product_commit);
  assert.deepEqual(retained.map(image=>image.file),['skills-use-clients.png']);
  for (const image of retained) {
    assert.equal(image.product_commit,'8254acd488c074ec30f660c68619e4039f52bb90');
    assert.ok(image.retained && image.retained.length>20,image.file);
  }
  assert.match(read('src/pages/docs/skills/use-in-agents.mdx'),/\[earlier five-client download capture\]\(\/images\/docs\/skills\/skills-use-clients\.png\)[^\n]*8254acd488c074ec30f660c68619e4039f52bb90/);
  const references=new Set(pages.flatMap(page=>[...read(`src/pages/docs/skills/${page}`).matchAll(/\/images\/docs\/skills\/([\w-]+\.png)/g)].map(match=>match[1])));
  assert.deepEqual(manifest.images.map(image=>image.file).sort(),[...references].sort());
  for (const image of manifest.images) {
    const bytes=fs.readFileSync(path.join(root,'public/images/docs/skills',image.file));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),image.sha256,image.file);
    assert.equal(bytes.readUInt32BE(16),image.width,image.file);
    assert.equal(bytes.readUInt32BE(20),image.height,image.file);
    assert.equal(image.width,1440,image.file);
    assert.equal(image.height,900,image.file);
  }
});

test('observed gates and distinct restoration semantics remain explicit', () => {
  assert.match(read('src/pages/docs/skills/campaigns.mdx'),/Repository rollouts are off/);
  assert.match(read('src/pages/docs/skills/tests.mdx'),/Application tests are off/);
  assert.match(read('src/pages/docs/skills/versions-and-labels.mdx'),/creates a new version even when those bytes match latest/);
  assert.match(read('src/pages/docs/skills/use-in-agents.mdx'),/not safe managed updaters/);
  assert.doesNotMatch(read('src/pages/docs/skills/index.mdx'),/does not include model test runs|no Skills methods/);
  assert.match(read('src/pages/docs/skills/sealed-api.mdx'),/schema-derived/);
});

test('current UI guidance preserves explicit review and restoration decisions', () => {
  const context=read('src/pages/docs/skills/agent-contexts.mdx');
  assert.match(context,/I've checked the 2 changed files against v1 and the 2 check warnings/);
  assert.match(context,/Publish version/);
  assert.match(context,/draft or published head changed/);
  const renewal=read('src/pages/docs/skills/reviewed-releases.mdx');
  for (const label of ['Connect an app','Approve again','Renew and decide later',"I've checked every change since the last approval"]) assert.ok(renewal.includes(label),label);
  const recovery=read('src/pages/docs/skills/rollout-recovery.mdx');
  assert.match(recovery,/current workspace or organization admin opens the Skills library's \*\*More > Archived skills/);
  assert.match(recovery,/I've checked which labels come back with this skill/);
  const all=pages.map(page=>read(`src/pages/docs/skills/${page}`)).join('\n');
  for (const stale of ['**Choose inventory packet**','**Create credential**','**Register application target**','**Preview whole-context test**','**Run whole-context test**','**Approve renewed revision**','**Verify on the application**','**Use** tab','**Consumers** tab','**Delivery: see Consumers**','**Used by**','I reviewed these changes against the current published version',"I've read the check warnings for this version",'**Request release review**','**Share evidence and prepare packet**','**Restore as a new version**','**Check updates**']) assert.ok(!all.includes(stale),`Stale UI label: ${stale}`);
});

test('CLI and SDK install guidance stays npm-only and makes no availability claim', () => {
  const sdk=read('src/pages/docs/skills/sdk-cli.mdx');
  assert.match(sdk,/npm install -g @future-agi\/cli/);
  assert.match(sdk,/npx -p @future-agi\/cli fagi/);
  assert.match(sdk,/Node\.js 22\.15 or later/);
  const all=[...pages.map(page=>read(`src/pages/docs/skills/${page}`)),...['register','context-helpers','semantic-conventions'].map(page=>read(`src/pages/docs/sdk/tracing/${page}.mdx`))].join('\n');
  for (const banned of ['brew install','Homebrew','install.sh','install.ps1','futureagi-cli/releases','fagi skills','@futureagi/sdk','npx futureagi-telemetry']) assert.ok(!all.includes(banned),`Unsupported install guidance: ${banned}`);
  assert.match(read('src/pages/docs/skills/trace-skills.mdx'),/SDK 0\.8\.0 or later/);
  assert.doesNotMatch(all,/(?:futureagi|@future-agi\/sdk) (?:0\.8\.0|0\.3\.0) (?:is|are) (?:now )?(?:released|available|published)/);
});

test('live examples retain statuses, source provenance, and secret redaction', () => {
  const evidence=JSON.parse(read('public/api/skills-examples.json'));
  // HTTP captures remain historical evidence; refreshing the schema must not relabel them.
  assert.equal(evidence.product_commit,'e503da41fd21655c94b7d46e64d202c44a886a47');
  assert.match(read('src/pages/docs/skills/sealed-api.mdx'),new RegExp(evidence.product_commit));
  assert.match(read('src/pages/docs/skills/sealed-api.mdx'),/not execution evidence for the current head/);
  assert.match(read('src/components/SkillsApiReference.astro'),/evidence\.product_commit/);
  assert.equal(evidence.synthetic,true);
  const successful=new Set();
  function visit(value) {
    if (!value || typeof value!=='object') return;
    for (const [key,child] of Object.entries(value)) {
      if (/^(secret|secret_key|api_key|access|refresh|token|credential)$/i.test(key)) assert.equal(child,'[redacted]',key);
      visit(child);
    }
  }
  for (const row of evidence.captures) {
    visit(row.request);visit(row.response);
    if (row.status>=200 && row.status<300) {
      const operation=contract.paths[row.contract_path]?.[row.method.toLowerCase()];
      assert.ok(operation,`${row.method} ${row.path}`);
      assert.ok(operation.responses[String(row.status)],`${row.method} ${row.path}: undocumented ${row.status}`);
      successful.add(`${row.method} ${row.contract_path}`);
    }
  }
  assert.ok(successful.size>=64);
});
