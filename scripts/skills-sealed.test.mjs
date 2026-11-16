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
  assert.equal(contract.provenance.product_commit,'e503da41fd21655c94b7d46e64d202c44a886a47');
  assert.equal(contract.provenance.sha256,'0d34c29112eb3571cfc0d436d3e113127de1a07eddd112bd7fb3a69154cecbe7');
  assert.equal(Object.keys(contract.paths).length,144);
  function visit(value) {
    if (!value || typeof value!=='object') return;
    if (value.$ref) assert.ok(contract.definitions[value.$ref.replace('#/definitions/','')],value.$ref);
    for (const child of Object.values(value)) visit(child);
  }
  visit(contract);
});

test('every sealed Skills operation is retained without rewriting its contract', () => {
  assert.ok(process.env.SKILLS_SOURCE_SWAGGER,'Set SKILLS_SOURCE_SWAGGER to the sealed product Swagger file');
  const source=JSON.parse(fs.readFileSync(process.env.SKILLS_SOURCE_SWAGGER,'utf8'));
  for (const field of ['basePath','consumes','produces','securityDefinitions','security']) assert.deepEqual(contract[field],source[field],field);
  const paths=Object.fromEntries(Object.entries(source.paths).filter(([route])=>route.startsWith('/model-hub/skills/')));
  assert.deepEqual(contract.paths,paths);
  for (const [name,schema] of Object.entries(contract.definitions)) assert.deepEqual(schema,source.definitions[name],name);
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
  assert.equal(manifest.product_commit,'03e18d08abdcc177c98415d6f3f2292d53c1661c');
  assert.equal(manifest.synthetic,true);
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
  assert.match(context,/I reviewed these changes against the current published version/);
  assert.match(context,/Publish version/);
  assert.match(context,/draft or published head changed/);
  const renewal=read('src/pages/docs/skills/reviewed-releases.mdx');
  for (const label of ['Connect an app','Approve again','Renew and decide later',"I've checked every change since the last approval"]) assert.ok(renewal.includes(label),label);
  const recovery=read('src/pages/docs/skills/rollout-recovery.mdx');
  assert.match(recovery,/workspace admin opens \*\*More → Archived skills/);
  assert.match(recovery,/I've checked which labels come back with this skill/);
  const all=pages.map(page=>read(`src/pages/docs/skills/${page}`)).join('\n');
  for (const stale of ['**Choose inventory packet**','**Create credential**','**Register application target**','**Preview whole-context test**','**Run whole-context test**','**Approve renewed revision**','**Verify on the application**','**Use** tab','**Consumers** tab','**Delivery: see Consumers**']) assert.ok(!all.includes(stale),`Stale UI label: ${stale}`);
});

test('live examples retain statuses, source provenance, and secret redaction', () => {
  const evidence=JSON.parse(read('public/api/skills-examples.json'));
  assert.equal(evidence.product_commit,contract.provenance.product_commit);
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
