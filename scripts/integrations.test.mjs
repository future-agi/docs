import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { integrations, integrationCategories, integrationNavigation, integrationAliases, integrationAids, integrationSearchText, integrationDirectoryMarkdown, validateIntegrations } from '../src/lib/integrations.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
function walk(dir) { return fs.readdirSync(dir, {withFileTypes:true}).flatMap(f => f.isDirectory() ? walk(path.join(dir,f.name)) : [path.join(dir,f.name)]); }
const routeFiles = walk(path.join(root,'src/pages')).filter(f => /\.(mdx|md|astro)$/.test(f));
const routes = new Set(routeFiles.map(f => '/'+path.relative(path.join(root,'src/pages'), f).replace(/\.(mdx|md|astro)$/, '').replace(/\/index$/, '')));
const redirects = new Map(Array.from(read('src/lib/redirects.ts').matchAll(/['"]([^'"]+)['"]:\s*['"]([^'"]+)['"]/g), m=>[m[1],m[2]]));
function exists(route, seen = new Set()) { if (routes.has(route)) return true; if (seen.has(route)) return false; seen.add(route); return redirects.has(route) && exists(redirects.get(route), seen); }
function flatten(list) { return list.flatMap(item => [item.href, ...(item.items ? flatten(item.items) : [])].filter(Boolean)); }
// Release labels are prose, not code samples, model names or package versions.
export function publicProse(text) { return text.replace(/^\s*(```|~~~)[\s\S]*?^\s*\1.*$/gm, '').replace(/`+[^`]*`+/g, ''); }

test('LlamaIndex guide installs the released current-core compatibility fix', () => {
  const page = read('src/pages/docs/integrations/traceai/llamaindex.mdx');
  assert.match(page, /pip install 'traceAI-llamaindex==0\.1\.10'/);
  assert.match(page, /https:\/\/pypi\.org\/pypi\/traceAI-llamaindex\/0\.1\.10\/json/);
});

test('catalog validates required fields, unique IDs/categories and route shape', () => {
  assert.equal(validateIntegrations(), true);
  for (const patch of [{id:'BAD'}, {href:'https://example.com'}, {category:'unknown'}, {name:''}, {summary:5}, {method:'Not tested'}, {method:'Alpha'}]) assert.throws(() => validateIntegrations([{...integrations[0],...patch}]));
  assert.throws(() => validateIntegrations([integrations[0],integrations[0]]));
  assert.equal(new Set(integrationCategories.map(c=>c.id)).size, integrationCategories.length);
});
test('every directory/sidebar target exists; every published integration route is discoverable', () => {
  const discovered = new Set([...integrations.map(i=>i.href), ...integrationAids.map(a=>a.href), '/docs/integrations', ...Object.keys(integrationAliases)]);
  for (const href of discovered) assert.ok(exists(href), `Missing route: ${href}`);
  for (const route of routes) if (route.startsWith('/docs/integrations/')) assert.ok(discovered.has(route), `Published guide missing from catalog: ${route}`);
  for (const [alias,target] of Object.entries(integrationAliases)) assert.ok(discovered.has(target) && exists(alias) && exists(target));
  assert.deepEqual(new Set(flatten(integrationNavigation)), new Set([...integrations.map(i=>i.href),...integrationAids.map(a=>a.href),'/docs/integrations']));
  assert.match(read('src/lib/navigation.ts'), /items: integrationNavigation/);
  assert.match(read('src/components/IntegrationDirectory.astro'), /integrationsInCategory\(category\.id\)/);
  assert.match(read('src/components/Sidebar.astro'), /integration-sidebar/);
});
test('the 24 recently published guides remain in both discovery surfaces', () => {
  const recent = ['frameworks/agentscope','frameworks/apollo-graphql','frameworks/embabel','frameworks/eve','frameworks/flue','frameworks/graphite','frameworks/koog','frameworks/mirascope','frameworks/open-agent-spec','frameworks/restate','frameworks/ruby-llm','frameworks/swiftide','frameworks/temporal','frameworks/watsonx-orchestrate-adk','gateways/envoy-ai-gateway','gateways/gravitee','gateways/kong-ai-gateway','gateways/litellm-proxy','gateways/vercel-ai-gateway','no-code/librechat','no-code/lobechat','providers/cometapi','providers/novita-ai','traceai/java/google-adk'];
  for (const slug of recent) assert.ok(integrations.some(i=>i.href===`/docs/integrations/${slug}`),slug);
});
test('frameworks, SDK vs proxy, and searchable historical names remain distinct', () => {
  for (const id of ['openai-agents','google-adk']) assert.equal(integrations.find(i=>i.id===id).category,'frameworks');
  assert.notEqual(integrations.find(i=>i.id==='litellm-sdk').href,integrations.find(i=>i.id==='litellm-proxy').href);
  for (const [query,id] of [['lobechat','lobechat'],['lobehub','lobechat'],['grafi','graphite'],['graphite','graphite'],['google adk java','java-google-adk']]) assert.ok(query.split(' ').every(t=>integrationSearchText(integrations.find(i=>i.id===id)).includes(t)));
});
test('all logo references have provenance, existing files, matching hashes and passive valid content', () => {
  const result = spawnSync('python3',[path.join(root,'scripts/validate-integration-logos.py')],{encoding:'utf8'});
  assert.equal(result.status,0,result.stdout+result.stderr);
  const manifest = JSON.parse(read('public/images/integrations/manifest.json'));
  for (const i of integrations) assert.ok(manifest.assets[i.logo],`Missing logo record: ${i.logo}`);
});
test('machine-readable overview serializes every catalog entry and setup aid', () => {
  const text = integrationDirectoryMarkdown();
  for (const entry of integrations) {
    assert.ok(text.includes(`[${entry.name}](${entry.href})`), entry.id);
    assert.ok(text.includes(entry.summary), entry.id);
    assert.ok(text.includes(entry.method), entry.id);
  }
  for (const aid of integrationAids) assert.ok(text.includes(`[${aid.name}](${aid.href})`));
  assert.equal(integrations.find(i => i.id === 'eve').name, 'Eve');
  assert.doesNotMatch(read('src/components/IntegrationDirectory.astro'), /↗/);
});
test('public prose and catalog labels contain no internal QA label or Alpha release status', () => {
  for (const file of routeFiles.filter(f=>f.endsWith('.mdx'))) {
    const prose=publicProse(fs.readFileSync(file,'utf8'));
    assert.doesNotMatch(prose,/\bnot\s+tested\b/i,file);
    assert.doesNotMatch(prose,/\balpha\b/i,file);
  }
  for (const item of [...integrations,...integrationCategories,...integrationAids]) assert.doesNotMatch(JSON.stringify(item),/\bnot\s+tested\b|\balpha\b/i);
  assert.equal(publicProse('Beta. `pkg==1.0.0-alpha`\n```python\nmodel="alpha"\n```\n'),'Beta. \n\n');
});
