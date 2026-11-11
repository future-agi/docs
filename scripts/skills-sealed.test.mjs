import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const contract = JSON.parse(read('public/api/skills-sealed.json'));
const pages = fs.readdirSync(path.join(root,'src/pages/docs/skills')).filter(f=>f.endsWith('.mdx'));

test('Skills API subset is pinned and has no dangling schema references', () => {
  assert.equal(contract.provenance.product_commit,'12576311b77d22f00c8ca1471c7f051eed96889a');
  assert.equal(contract.provenance.sha256,'c06b8610ccba9ffe52b1a428e5f481f8a016cbb8f8f94250583d3ff47da58230');
  assert.equal(Object.keys(contract.paths).length,129);
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
  for (const name of ['context-linked-skills','context-accepted-lock','exact-release-review','durable-release-receipt','context-historical-editor','campaign-boundary','retained-migration','github-import','context-detail','context-use']) {
    const bytes=fs.readFileSync(path.join(root,`public/images/docs/skills/${name}.png`));
    assert.equal(bytes.readUInt32BE(16),1440,name);
    assert.equal(bytes.readUInt32BE(20),900,name);
  }
});

test('observed gates and distinct restoration semantics remain explicit', () => {
  assert.match(read('src/pages/docs/skills/campaigns.mdx'),/Repository rollouts \(unavailable\)/);
  assert.match(read('src/pages/docs/skills/tests.mdx'),/Tests\*\* disabled/);
  assert.match(read('src/pages/docs/skills/versions-and-labels.mdx'),/creates a new version even when those bytes match latest/);
  assert.match(read('src/pages/docs/skills/use-in-agents.mdx'),/not safe managed updaters/);
  assert.doesNotMatch(read('src/pages/docs/skills/index.mdx'),/does not include model test runs|no Skills methods/);
  assert.match(read('src/pages/docs/skills/sealed-api.mdx'),/schema-derived/);
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
