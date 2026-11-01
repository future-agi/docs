import './langsmith-page.test.mjs';
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
test('Apollo Router stays distinct from Server and documents the native HTTP trace contract', () => {
  const router = integrations.find(item => item.id === 'apollo-router');
  assert.equal(router.method, 'OpenTelemetry');
  assert.notEqual(router.href, integrations.find(item => item.id === 'apollo-graphql').href);
  const page = read('src/pages/docs/integrations/frameworks/apollo-router.mdx');
  const yaml = page.match(/```yaml\n([\s\S]*?)\n```/)?.[1];
  assert.ok(yaml, 'Native YAML configuration is required');
  for (const setting of [
    'mode: spec_compliant', 'default_attribute_requirement_level: none',
    'protocol: http', 'endpoint: https://api.futureagi.com/tracer/v1/traces',
    'project_name: ${env.FI_PROJECT_NAME}', 'project_type: observe',
    'X-Api-Key: ${env.FI_API_KEY}', 'X-Secret-Key: ${env.FI_SECRET_KEY}',
    'parent_based_sampler: true', 'trace_context: true',
  ]) assert.ok(yaml.includes(setting), setting);
  assert.doesNotMatch(yaml, /graphql\.document:\s*true|metrics:|logging:/);
  assert.match(page, /v2\.19\.0/);
  assert.match(page, /query RouterCheck \{ __typename \}/);
  assert.ok(fs.existsSync(path.join(root, 'public/images/product-guides/apollo-router-observe.png')));
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
test('Together OpenAI guide requires the released provider mapping without claiming native SDK coverage', () => {
  const page = read('src/pages/docs/integrations/traceai/togetherai.mdx');
  assert.match(page, /pip install --upgrade "traceAI-openai>=0\.1\.11" "fi-instrumentation-otel>=1\.2\.2"/);
  assert.match(page, /base_url="https:\/\/api\.together\.ai\/v1"/);
  assert.match(page, /gen_ai\.provider\.name=together/);
  assert.match(page, /does not instrument an existing `together\.Together` client/);
  assert.doesNotMatch(page, /can be labeled \*\*OpenAI\*\*|Do not rely on that field/);
});

test('Cloudflare AI Chat distinguishes span identity from trace-level session grouping', () => {
  const page = read('src/pages/docs/integrations/frameworks/cloudflare-ai-chat.mdx');
  assert.doesNotMatch(page, /use the session to see it whole/i);
  assert.match(page, /span-level correlation/i);
  assert.match(page, /trace-level session grouping requires[^.]*root span/i);
  assert.match(page, /does not propagate[^.]*runtime roots/i);
  assert.match(page, /open each message trace/i);
});

test('Vertex AI recommends Google Gen AI and keeps bounded legacy migration guidance', () => {
  const page = read('src/pages/docs/integrations/traceai/vertexai.mdx');
  const recommended = page.split('## Migrate an existing Vertex AI SDK app')[0];
  assert.match(recommended, /pip install traceAI-google-genai google-genai/);
  assert.match(recommended, /from traceai_google_genai import GoogleGenAIInstrumentor/);
  assert.match(recommended, /vertexai=True/);
  assert.match(recommended, /gcloud auth application-default login/);
  for (const variable of ['GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION', 'GOOGLE_GENAI_MODEL']) {
    assert.ok(recommended.includes(`export ${variable}=`));
    assert.ok(recommended.includes(`os.environ["${variable}"]`));
  }
  assert.match(recommended, /trace_provider\.force_flush\(\)/);
  assert.doesNotMatch(recommended, /from vertexai|import vertexai|traceAI-vertexai/);
  assert.doesNotMatch(page, /pip install vertexai\b|gemini-1\.5-flash/);
  assert.match(page, /google-cloud-aiplatform>=1\.61\.0,<=1\.101\.0/);
  assert.match(page, /pip install traceAI-vertexai 'google-cloud-aiplatform==1\.101\.0'/);
  assert.match(page, /before importing `vertexai`/);
  assert.match(page, /does not restore retired models/);
  assert.match(page, /FI_HIDE_INPUTS=true/);
  assert.match(page, /FI_HIDE_OUTPUTS=true/);
});

test('Anthropic Java recommends one native tracing owner and preserves released legacy usage', () => {
  const page = read('src/pages/docs/integrations/traceai/java/anthropic.mdx');
  const native = page.split('## Existing TracedAnthropicClient applications')[0];
  assert.match(native, /opentelemetry-bom/);
  assert.match(native, /1\.57\.0/);
  assert.match(native, /OpenTelemetryContentMode\.METADATA_ONLY/);
  assert.match(native, /W3CTraceContextPropagator/);
  assert.match(native, /X-Project-Name/);
  assert.match(native, /client\.messages\(\)\.create\(/);
  assert.doesNotMatch(native, /new TracedAnthropicClient/);
  assert.match(page, /<groupId>com\.futureagi<\/groupId>/);
  assert.match(page, /\.openTelemetry\(false\)/);
  assert.doesNotMatch(page, /main-SNAPSHOT|wrapper is incompatible/);
  assert.equal(integrations.find(i => i.id === 'java-anthropic').method, 'OpenTelemetry');
  for (const [, route] of page.matchAll(/\]\((\/docs\/[^)#]+)(?:#[^)]*)?\)/g)) {
    assert.ok(exists(route), `Missing guide link: ${route}`);
  }
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
