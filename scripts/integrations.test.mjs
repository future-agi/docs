import './pi-plugin-page.test.mjs';
import './openclaw-package-page.test.mjs';
import './goose-page.test.mjs';
import './copilot-page.test.mjs';
import './coding-agents-contract.test.mjs';
import './cursor-page.test.mjs';
import './google-antigravity-page.test.mjs';
import './codex-page.test.mjs';
import './opencode-page.test.mjs';
import './claude-code-page.test.mjs';
import './codex-sdk-page.test.mjs';
import './augment-code-page.test.mjs';
import './gemini-cli-page.test.mjs';
import './semantic-kernel-page.test.mjs';
import './flowise-page.test.mjs';
import './ollama-java.test.mjs';
import './azure-openai-java.test.mjs';
import './langsmith-page.test.mjs';
import './exa-page.test.mjs';
import './langchain-deep-agents-page.test.mjs';
import './vercel-platform-page.test.mjs';
import './scalekit-page.test.mjs';
import './eino-page.test.mjs';
import './devin-page.test.mjs';
import './pi-sdk-page.test.mjs';
import './cursor-sdk-page.test.mjs';
import './grok-build-page.test.mjs';
import './hermes-agent-page.test.mjs';
import './kiro-cli-page.test.mjs';
import './google-genai-live-page.test.mjs';
import './elevenlabs-agents-page.test.mjs';
import './gemini-go-page.test.mjs';
import './typesafe-page.test.mjs';
import './ag2-classic-page.test.mjs';
import './firecrawl-page.test.mjs';
import './parallel-page.test.mjs';
import './otel-genai-page.test.mjs';
import './genkit-page.test.mjs';
import './trace-config-page.test.mjs';
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

test('VoltAgent uses the released processor and a discoverable Node.js example', () => {
  const page = read('src/pages/docs/integrations/traceai/voltagent.mdx');
  const catalog = integrations.find(i => i.id === 'voltagent');
  assert.equal(catalog?.href, '/docs/integrations/traceai/voltagent');
  assert.equal(catalog?.category, 'frameworks');
  assert.equal(catalog?.method, 'traceAI SDK');
  for (const pin of ['@traceai/voltagent@0.1.0', '@traceai/fi-core@1.1.1', '@voltagent/core@2.11.0', 'ai@6.0.309', '@ai-sdk/openai@3.0.130', 'zod@4.6.7']) {
    assert.ok(page.includes(pin), pin);
  }
  assert.match(page, /setGlobalTracerProvider: false/);
  assert.match(page, /spanProcessors: \[new FIVoltAgentSpanProcessor\(\{ tracerProvider \}\)\]/);
  assert.match(page, /node voltagent\.mjs/);
  assert.match(page, /Open \*\*Observe\*\*/);
  assert.doesNotMatch(page, /tested with|live run|unit tests|end-to-end runs|2026-10-16/i);
});

test('VoltAgent closes the application and owned provider even when the operation fails', () => {
  const page = read('src/pages/docs/integrations/traceai/voltagent.mdx');
  const example = page.match(/```javascript\n([\s\S]*?)\n```/)?.[1];
  assert.ok(example, 'A runnable example is required');
  assert.match(example, /const app = new VoltAgent\(/);
  assert.match(example, /try \{\s*const result = await agent\.generateText\(/);
  assert.match(example, /\} finally \{\s*try \{\s*await app\.shutdown\(\);\s*\} finally \{\s*\/\/[^\n]*\n\s*await tracerProvider\.shutdown\(\);\s*\}\s*\}/);
  assert.doesNotMatch(example, /await observability\.(?:shutdown|forceFlush)\(\)|process\.exit/);
  assert.match(page, /`observability\.shutdown\(\)` alone does not stop all application resources/);
  assert.match(page, /full application and owned-provider cleanup/);
  assert.match(page, /await observability\.forceFlush\(\)/);
  assert.match(page, /not after each request/);
});

test('VoltAgent keeps actionable resumed-workflow, token and privacy limits', () => {
  const page = read('src/pages/docs/integrations/traceai/voltagent.mdx');
  assert.match(page, /Resumed workflows in VoltAgent 2\.11\.0/);
  assert.match(page, /500 ms polling interval.*even after `app\.shutdown\(\)`/);
  assert.match(page, /Do not force-exit a server or manipulate private timers/);
  assert.match(page, /actual success or failure status/);
  assert.match(page, /flush before the agent span ends/);
  assert.match(page, /FI_HIDE_INPUTS=true/);
  assert.match(page, /FI_HIDE_OUTPUTS=true/);
  assert.match(page, /JSON-valued attributes.*can retain nested credentials/);
  assert.match(page, /`FI_PII_REDACTION` is not applied/);
  assert.match(page, /not VoltOps or other exporters/);
  assert.doesNotMatch(page, /Credentials are never exported/);
});

test('Vitest guide documents native test tracing without an evaluation-import claim', () => {
  const page = read('src/pages/docs/integrations/frameworks/vitest.mdx');
  const catalog = integrations.find(i => i.id === 'vitest');
  const example = read('examples/frameworks/vitest/otel.mjs');
  assert.equal(catalog?.method, 'Native OTLP');
  assert.match(page, /5\.0\.5 or later/);
  assert.match(page, /experimental:\s*\{/);
  assert.match(page, /sdkPath: '\.\/otel\.mjs'/);
  assert.match(page, /project_name: process\.env\.FI_PROJECT_NAME/);
  assert.match(page, /https:\/\/api\.futureagi\.com\/tracer\/v1\/traces/);
  assert.match(page, /does not turn tests into Future AGI evaluations/);
  assert.match(example, /export default sdk/);
  assert.doesNotMatch(page, /@traceai\/vitest|verified live|test date/i);
});

test('AG2 guide uses released native-middleware setup without a public test diary', () => {
  const page = read('src/pages/docs/integrations/traceai/ag2.mdx');
  const entry = integrations.find(item => item.id === 'ag2');
  assert.equal(entry?.href, '/docs/integrations/traceai/ag2');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'OTel + traceAI');
  for (const setting of [
    '"traceAI-ag2==0.1.0"', '"ag2[openai]==1.1.2"', '"fi-instrumentation-otel==1.2.3"',
    'from traceai_ag2 import setup', 'setup(agent, tracer_provider=trace_provider)',
    'project_type=ProjectType.OBSERVE', 'with using_session("weather-example"):',
    'python ag2_example.py',
  ]) assert.ok(page.includes(setting), setting);
  assert.match(page, /finally:\n    trace_provider\.force_flush\(\)\n    trace_provider\.shutdown\(\)/);
  const capture = page.split('## 3. Run an instrumented agent')[0];
  assert.match(capture, /FI_HIDE_INPUTS=true/);
  assert.match(capture, /FI_HIDE_OUTPUTS=true/);
  assert.match(capture, /before initializing tracing/);
  assert.match(capture, /do not redact arbitrary custom attributes/);
  assert.match(capture, /custom concurrent processor can export spans before content filtering/);
  assert.match(page, /This is not general personal-data redaction/);
  assert.match(page, /## 4\. View the trace/);
  assert.doesNotMatch(page, /tested with|offline test|latest stable|verified live|\balpha\b|2026-\d{2}-\d{2}/i);
});

test('LlamaIndex distinguishes deprecated TypeScript from the supported Python guide', () => {
  const page = read('src/pages/docs/integrations/traceai/llamaindex.mdx');
  const notice = page.split('## Install')[0];
  assert.match(notice, /LlamaIndex\.TS is deprecated and no longer maintained upstream/);
  assert.match(notice, /https:\/\/github\.com\/run-llama\/LlamaIndexTS#deprecation-notice/);
  assert.match(notice, /`@traceai\/llamaindex` TypeScript integration is deprecated/);
  assert.match(notice, /Python integration is not deprecated/);
  assert.match(notice, /not a drop-in replacement/);
  assert.doesNotMatch(page, /npm install.*@traceai\/llamaindex|@traceai\/llamaindex@0\.2\.0/);
});

test('LlamaIndex guide installs the released current-core compatibility fix', () => {
  const page = read('src/pages/docs/integrations/traceai/llamaindex.mdx');
  assert.match(page, /pip install 'traceAI-llamaindex==0\.1\.10'/);
  assert.match(page, /https:\/\/pypi\.org\/pypi\/traceAI-llamaindex\/0\.1\.10\/json/);
});

test('OpenAI C# guide uses native chat tracing with authenticated traces-only export', () => {
  const page = read('src/pages/docs/integrations/providers/openai-csharp.mdx');
  const catalog = integrations.find(i => i.id === 'openai-csharp');
  assert.equal(catalog?.method, 'Native OTLP');
  assert.match(page, /AppContext.SetSwitch\("OpenAI.Experimental.EnableOpenTelemetry", true\)/);
  assert.match(page, /\.AddSource\("OpenAI.ChatClient", "OpenAIChat.Application"\)/);
  assert.match(page, /OtlpExportProtocol.HttpProtobuf/);
  assert.match(page, /https:\/\/api.futureagi.com\/tracer\/v1\/traces/);
  assert.match(page, /X-Api-Key=\{apiKey\},X-Secret-Key=\{secretKey\}/);
  assert.match(page, /\["project_name"\] = project/);
  assert.match(page, /\["project_type"\] = "observe"/);
  assert.match(page, /error descriptions can include text/);
  assert.match(page, /streaming chat, raw\/protocol calls, Responses, embeddings/);
  assert.doesNotMatch(page, /TraceAI.Register|AddOtlpMetricExporter|AddOtlpLogExporter/);
});

test('Python AI SDK guide exports authenticated native OTLP spans with content capture disabled', () => {
  const guide = integrations.find(item => item.id === 'vercel-ai-sdk-python');
  assert.equal(guide?.method, 'OpenTelemetry');
  assert.notEqual(guide.href, integrations.find(item => item.id === 'vercel-ai-sdk').href);
  const page = read('src/pages/docs/integrations/frameworks/vercel-ai-sdk-python.mdx');
  for (const setting of [
    'ai[openai,otel]>=0.4.0,<0.9', 'register(OtelAdapter(tracer_provider=provider, capture_content=False))',
    'https://api.futureagi.com/tracer/v1/traces', '"project_name": os.environ["FI_PROJECT_NAME"]',
    '"project_type": "observe"', '"x-api-key": os.environ["FI_API_KEY"]',
    '"x-secret-key": os.environ["FI_SECRET_KEY"]', 'provider.shutdown()',
  ]) assert.ok(page.includes(setting), setting);
  assert.match(page, /exception text in the span's error status/);
  assert.doesNotMatch(page, /traceAI-[a-z]+|from traceai_/);
});

test('Python AI SDK guide limits the content exclusion guarantee and discloses tool metadata', () => {
  const page = read('src/pages/docs/integrations/frameworks/vercel-ai-sdk-python.mdx');
  const privacy = page.split('## Content and privacy')[1]?.split('## Troubleshooting')[0];
  assert.ok(privacy, 'Keep the native content and privacy guidance');
  assert.match(privacy, /`capture_content=False` keeps prompt and completion messages, tool arguments and tool results out/);
  assert.doesNotMatch(privacy, /`capture_content=False` keeps[^.]*tool definitions/);
  assert.match(privacy, /Tool names and descriptions, including tool docstrings, are exported independently of `capture_content`/);
  assert.match(privacy, /Remove sensitive text from tool names and descriptions/);
  assert.match(privacy, /OpenTelemetry Collector configured to redact those attributes before forwarding to Future AGI/);
  assert.match(privacy, /exception text in the span's error status/);
  assert.match(privacy, /custom span attributes or events you add yourself/);
});

test('Python AI SDK guide explains the native masking boundary beside content opt-in', () => {
  const page = read('src/pages/docs/integrations/frameworks/vercel-ai-sdk-python.mdx');
  const privacy = page.split('## Content and privacy')[1]?.split('## Troubleshooting')[0];
  const optIn = privacy?.split(/\n\s*\n/).find(paragraph => paragraph.includes('`capture_content=True`'));
  assert.ok(optIn, 'Keep the masking boundary beside the content opt-in');
  for (const setting of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS']) {
    assert.ok(optIn.includes(`\`${setting}\``), `Explain the native boundary for ${setting}`);
  }
  assert.match(optIn, /other traceAI masking settings do not sanitize this native OpenTelemetry route/);
  assert.match(optIn, /native content controls and your pre-export redaction policy/);
  assert.match(optIn, /do not rely on `FI_HIDE_\*` to filter captured payloads/);
  const troubleshooting = page.split('## Troubleshooting')[1];
  assert.match(troubleshooting, /\[content and privacy\]\(#content-and-privacy\) before switching to `capture_content=True`/);
  assert.match(troubleshooting, /`FI_HIDE_\*` settings do not filter this native route/);
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

test('Apollo Router warns about native subgraph URL attributes before direct export', () => {
  const page = read('src/pages/docs/integrations/frameworks/apollo-router.mdx');
  const prerequisites = page.split('## Configure native tracing')[0];
  assert.match(prerequisites, /Remove credentials and sensitive values from subgraph endpoint URLs/);
  assert.match(prerequisites, /authentication headers instead/);
  const warning = [...page.matchAll(/<Warning>([\s\S]*?)<\/Warning>/g)]
    .map(match => match[1]).find(text => text.includes('`http.url`'));
  assert.ok(warning, 'The privacy warning must describe native URL attributes');
  assert.match(warning, /complete subgraph endpoint URLs, including query strings/);
  for (const span of ['http_request', 'subgraph_request']) {
    assert.ok(warning.includes(`\`${span}\``), `Missing native span: ${span}`);
  }
  assert.match(warning, /even with `default_attribute_requirement_level: none`/);
  assert.match(warning, /removing content selectors does not remove these attributes/);
  assert.match(warning, /OpenTelemetry Collector/);
  assert.match(warning, /remove or redact sensitive span attributes before forwarding/);
  assert.match(warning, /do not export directly/);
  assert.doesNotMatch(page, /structure-only configuration/);
});

test('all logo references have provenance, existing files, matching hashes and passive valid content', () => {
  const result = spawnSync('python3',[path.join(root,'scripts/validate-integration-logos.py')],{encoding:'utf8'});
  assert.equal(result.status,0,result.stdout+result.stderr);
  const manifest = JSON.parse(read('public/images/integrations/manifest.json'));
  for (const i of integrations) assert.ok(manifest.assets[i.logo],`Missing logo record: ${i.logo}`);
});
test('Qdrant Java uses released Central coordinates and a complete blocking example', () => {
  const page = read('src/pages/docs/integrations/traceai/java/vector-databases.mdx');
  const section = page.split('## Qdrant\n')[1].split('\n## Milvus')[0];
  assert.match(section, /<groupId>com\.futureagi<\/groupId>/);
  assert.match(section, /<artifactId>traceai-java-qdrant<\/artifactId>\s*<version>1\.0\.0<\/version>/);
  assert.match(section, /implementation 'com\.futureagi:traceai-java-qdrant:1\.0\.0'/);
  assert.match(section, /implementation 'io\.qdrant:client:1\.16\.2'/);
  const gradle = section.match(/```groovy Gradle\n([\s\S]*?)```/)[1];
  assert.match(gradle, /repositories\s*\{\s*mavenCentral\(\)\s*\}/);
  assert.match(gradle, /dependencies\s*\{/);
  assert.doesNotMatch(gradle, /traceai-java-core/);
  assert.match(page, /For Qdrant, follow the Maven Central installation below \*\*instead of\*\* that page's JitPack installation/);
  assert.match(section, /Replace any existing JitPack TraceAI core and Qdrant dependencies/);
  assert.match(section, /com\.futureagi:traceai-java-core:1\.0\.0` transitively/);
  assert.doesNotMatch(section, /main-SNAPSHOT|com\.github\.future-agi/);
  assert.match(section, /blocking methods/);
  assert.match(section, /unwrap\(\).*bypass/);
  assert.match(section, /public class QdrantExample/);
  assert.match(section, /import io\.qdrant\.client\.grpc\.Collections\.Distance;/);
  assert.match(section, /TraceAI\.shutdown\(\)/);
  assert.doesNotMatch(section, /queryVector|pointsList|queryAsync\(/);
});
test('Qdrant Java configures export and discloses the pinned upsert metadata limitation', () => {
  const page = read('src/pages/docs/integrations/traceai/java/vector-databases.mdx');
  const section = page.split('## Qdrant\n')[1].split('\n## Milvus')[0];
  const environment = section.match(/```bash\n([\s\S]*?)```/)[1];
  assert.match(environment, /^export FI_BASE_URL="https:\/\/api\.futureagi\.com"$/m);
  assert.match(environment, /^export FI_API_KEY="your-fi-api-key"$/m);
  assert.match(environment, /^export FI_SECRET_KEY="your-fi-secret-key"$/m);
  assert.match(section, /credentials alone do not enable span export/);
  assert.match(section, /<Warning>\s*With `traceai-java-qdrant:1\.0\.0` and Qdrant SDK `1\.16\.2`/);
  assert.match(section, /"Qdrant Upsert" spans incorrectly report `embedding\.dimensions` as `0`/);
  assert.match(section, /Do not rely on this upsert field/);
  assert.match(section, /use your collection configuration instead/);
  assert.match(page, /\| `embedding\.dimensions` \|[^\n]*\[Qdrant limitation\]\(#qdrant\)/);
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
test('MongoDB Java setup uses matching pinned Maven Central dependencies in both build tools', () => {
  const section = read('src/pages/docs/integrations/traceai/java/vector-databases.mdx')
    .split('## MongoDB Atlas Vector Search\n')[1]?.split('\n## Redis')[0];
  assert.ok(section, 'MongoDB setup section must exist');
  const maven = section.match(/```xml Maven\n([\s\S]*?)```/)?.[1];
  const gradle = section.match(/```groovy Gradle\n([\s\S]*?)```/)?.[1];
  assert.ok(maven && gradle, 'Both build tools need installation snippets');
  const dependencies = [...maven.matchAll(/<dependency>([\s\S]*?)<\/dependency>/g)]
    .map(([, block]) => ['groupId', 'artifactId', 'version']
      .map(tag => block.match(new RegExp(`<${tag}>([^<]+)</${tag}>`))?.[1]).join(':'));
  assert.deepEqual(dependencies, [
    'com.futureagi:traceai-java-core:1.0.0',
    'com.futureagi:traceai-java-mongodb:1.0.0',
    'org.mongodb:mongodb-driver-sync:5.14.0',
  ]);
  assert.deepEqual([...gradle.matchAll(/implementation '([^']+)'/g)].map(([, coordinate]) => coordinate), dependencies);
  assert.match(gradle, /mavenCentral\(\)/);
  assert.doesNotMatch(maven + gradle, /main-SNAPSHOT|com\.github\.future-agi/);
});

test('MongoDB Java setup keeps initialization and explicit vector-search scope clear', () => {
  const section = read('src/pages/docs/integrations/traceai/java/vector-databases.mdx')
    .split('## MongoDB Atlas Vector Search\n')[1]?.split('\n## Redis')[0];
  assert.ok(section, 'MongoDB setup section must exist');
  assert.match(section, /Replace any JitPack core or MongoDB dependencies/);
  assert.match(section, /\/docs\/integrations\/traceai\/java#initialization/);
  assert.match(section, /only operations called through the wrapper/);
  assert.match(section, /import java\.util\.List;/);
  assert.match(section, /List<Double> queryVector/);
  assert.match(section, /collection\.getNamespace\(\)\.getCollectionName\(\)/);
  assert.doesNotMatch(section, /\/\* your MongoDB collection \*\//);
});

test('Envoy native OTLP endpoints retain the Future AGI receiver prefix', () => {
  const page = read('src/pages/docs/integrations/gateways/envoy-ai-gateway.mdx');
  const cloud = page.match(/export OTEL_EXPORTER_OTLP_ENDPOINT="([^"]+)"/)?.[1];
  const selfHosted = page.match(/# self-hosted: (\S+)/)?.[1];
  assert.equal(cloud, 'https://api.futureagi.com/tracer');
  assert.equal(selfHosted, 'http://<collector>:4318/tracer');
  // Generic OTLP HTTP endpoints are base URLs, not full signal endpoints.
  for (const base of [cloud, selfHosted.replace('<collector>', 'localhost')]) {
    assert.equal(new URL(`${base}/v1/traces`).pathname, '/tracer/v1/traces');
  }
});
test('Envoy guide distinguishes propagated spans from separate traces', () => {
  const page = read('src/pages/docs/integrations/gateways/envoy-ai-gateway.mdx');
  assert.doesNotMatch(page, /Running both gives two traces/);
  assert.match(page, /traceparent/);
  assert.match(page, /same trace/);
  assert.match(page, /Without propagated context/);
});
test('Envoy guide keeps native tracing and content-safe trace-only defaults', () => {
  const page = read('src/pages/docs/integrations/gateways/envoy-ai-gateway.mdx');
  assert.match(page, /no Future AGI package/);
  assert.match(page, /OTEL_EXPORTER_OTLP_PROTOCOL="http\/protobuf"/);
  for (const signal of ['METRICS', 'LOGS']) assert.ok(page.includes(`OTEL_${signal}_EXPORTER="none"`));
  for (const field of ['INPUTS', 'OUTPUTS', 'EMBEDDINGS_TEXT', 'EMBEDDINGS_VECTORS']) {
    assert.ok(page.includes(`OPENINFERENCE_HIDE_${field}=true`));
  }
  assert.match(page, /do not hide error status messages/);
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

test('Claude Agent SDK TypeScript uses released packages and framework discovery', () => {
  const page = read('src/pages/docs/integrations/traceai/claude-agent-sdk-typescript.mdx');
  const entry = integrations.find(i => i.id === 'claude-agent-sdk-typescript');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI SDK');
  assert.equal(entry?.href, '/docs/integrations/traceai/claude-agent-sdk-typescript');
  assert.equal(entry?.logo, 'anthropic');
  assert.match(page, /npm install @traceai\/claude-agent-sdk@0\.1\.0 @traceai\/fi-core@1\.1\.1 @anthropic-ai\/claude-agent-sdk@0\.3\.302/);
  assert.match(page, /Node\.js 22 or later/);
  assert.match(page, /launch the SDK's CLI subprocess/);
  assert.doesNotMatch(publicProse(page), /tested with|latest on npm|not tested|\balpha\b|2026-10-16/i);
});

test('Claude Agent SDK example wraps query and flushes on the error path', () => {
  const page = read('src/pages/docs/integrations/traceai/claude-agent-sdk-typescript.mdx');
  const example = page.match(/```javascript\n([\s\S]*?)\n```/)?.[1];
  assert.ok(example, 'Keep the runnable ESM application example');
  assert.match(example, /wrapQuery\(query, \{ tracerProvider \}\)/);
  assert.match(example, /projectName: "my-agent"/);
  assert.match(example, /tools: \["Read"\], allowedTools: \["Read"\]/);
  assert.match(example, /finally \{\s*await shutdown\(\)/);
  assert.match(page, /> notes\.txt\nnode agent\.mjs/);
  assert.match(page, /Open \*\*Observe\*\*/);
  assert.match(page, /otherwise it joins the caller's trace/);
  assert.match(page, /\.\.\.process\.env, ANTHROPIC_BASE_URL:/);
});

test('Claude Agent SDK retains actionable privacy and usage limits', () => {
  const page = read('src/pages/docs/integrations/traceai/claude-agent-sdk-typescript.mdx');
  assert.match(page.split('## 3.')[0], /Content is captured by default/);
  for (const setting of ['FI_HIDE_INPUTS=true', 'FI_HIDE_OUTPUTS=true', 'hideInputs: true', 'hideOutputs: true']) {
    assert.ok(page.includes(setting), setting);
  }
  assert.match(page, /do not remove arbitrary secrets or all personal data/);
  assert.match(page, /Span names, tool names, session IDs and other structural metadata remain/);
  assert.match(page, /keep one session on one process/);
  assert.match(page, /claude_agent\.usage\.baseline_unknown=true/);
  assert.doesNotMatch(page, /user names and host names are not exported/);
});

test('Anthropic recommends native SDK tracing in both languages and keeps the Python instrumentor route', () => {
  const page = read('src/pages/docs/integrations/traceai/anthropic.mdx');
  const python = [...page.matchAll(/```(?:bash|python) Python\n([\s\S]*?)```/g)].map(m => m[1]).join('\n');
  assert.match(python, /pip install "anthropic>=1\.14\.0" fi-instrumentation-otel/);
  assert.match(python, /"tracer_provider": trace_provider/);
  assert.match(python, /"content_mode": "metadata_only"/);
  assert.match(python, /trace_provider\.shutdown\(\)/);
  assert.doesNotMatch(python, /traceai_anthropic|AnthropicInstrumentor|traceAI-anthropic/);
  const legacy = page.split('## Keep AnthropicInstrumentor in Python')[1];
  assert.ok(legacy, 'missing instrumentor section');
  assert.match(legacy, /AnthropicInstrumentor\(\)\.instrument\(tracer_provider=trace_provider\)/);
  assert.match(legacy, /anthropic\.Anthropic\(open_telemetry=False\)/);
  assert.match(page, /\(#keep-anthropicinstrumentor-in-python\)/);
  // The native route says that context helpers don't reach the SDK's spans.
  const native = page.split('## Keep AnthropicInstrumentor in Python')[0];
  assert.match(native, /context helpers\]\(\/docs\/sdk\/tracing\/context-helpers\)[^\n]*`using_session`[^\n]*`using_attributes`/);
  assert.match(native, /session, user, metadata or tags/);
  // The released SDK's native tracing works without the old adapter's conflicting peer range.
  const typescriptInstall = page.match(/```bash JS\/TS\n([\s\S]*?)```/)?.[1].trim();
  assert.equal(typescriptInstall, 'npm install @anthropic-ai/sdk@1.4.0 @traceai/fi-core');
  const typescript = [...page.matchAll(/```typescript JS\/TS\n([\s\S]*?)```/g)].map(m => m[1]).join('\n');
  assert.match(typescript, /openTelemetry:\s*\{\s*tracerProvider,/);
  assert.match(typescript, /traces: \{ contentMode: "metadata_only" \}/);
  assert.match(typescript, /await tracerProvider\.shutdown\(\)/);
  assert.doesNotMatch(typescript, /AnthropicInstrumentation|registerInstrumentations|manuallyInstrument/);
  assert.match(native, /npm uninstall @traceai\/anthropic/);
  assert.match(native, /`TraceConfig` and `FI_HIDE_\*` settings don't apply/);
  assert.match(native, /TypeScript's `contentMode`/);
  assert.doesNotMatch(page, /sdk@\^0\.27\.3|Keep that SDK range/);
  assert.equal(integrations.find(i => i.id === 'anthropic').method, 'OpenTelemetry');
  for (const [, route] of page.matchAll(/\]\((\/docs\/[^)#]+)(?:#[^)]*)?\)/g)) {
    assert.ok(exists(route), `Missing guide link: ${route}`);
  }
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

test('Java pgvector uses released Central packages and connection-local type registration', () => {
  const page = read('src/pages/docs/integrations/traceai/java/vector-databases.mdx');
  const section = page.split('## pgvector\n')[1].split('## Azure AI Search')[0];
  assert.match(section, /com\.futureagi:traceai-java-pgvector:1\.0\.0/);
  assert.match(section, /com\.pgvector:pgvector:0\.1\.6/);
  assert.match(section, /org\.postgresql:postgresql:42\.7\.14/);
  assert.doesNotMatch(section, /main-SNAPSHOT|com\.github\.future-agi/);
  assert.match(section, /try \(Connection connection = ds\.getConnection\(\)\)/);
  assert.match(section, /new TracedPgVectorStore\(connection\)/);
  assert.match(section, /PGvector\.registerTypes\(connection\)/);
  assert.ok(section.indexOf('PGvector.registerTypes(connection)') < section.indexOf('traced.search('));
  assert.match(section, /each connection/);
  assert.match(section, /arbitrary SQL/);
  assert.match(section, /never concatenate untrusted input/);
  assert.match(section, /float\[\] vector = \{1\.0f, 2\.0f, 3\.0f\}/);
});

test('Java pgvector qualifies successful-operation privacy and hides database error details before use', () => {
  const page = read('src/pages/docs/integrations/traceai/java/vector-databases.mdx');
  const section = page.split('## pgvector\n')[1].split('## Azure AI Search')[0];
  assert.match(section, /During successful operations, the store does not add embeddings or document metadata as span attributes/);
  assert.doesNotMatch(section, /Embeddings and document metadata are not added to these spans/);
  assert.match(section, /PostgreSQL error details can contain row values, including embeddings and document metadata/);
  assert.match(section, /`FI_HIDE_ERROR_DETAILS=true` before initializing TraceAI/);
  assert.match(section, /TraceConfig\.builder\(\)\.hideErrorDetails\(true\)\.build\(\)/);
  assert.match(section, /`TraceAI\.init\(\.\.\.\)`/);
  assert.match(section, /error messages, stack traces, and status descriptions/);
  assert.match(section, /preserving ERROR status and exception types/);
  assert.ok(section.indexOf('FI_HIDE_ERROR_DETAILS=true') < section.indexOf('new TracedPgVectorStore(connection)'));
});

test('OpenAI Go guide is discoverable and bootstraps the released module', () => {
  const page = read('src/pages/docs/integrations/traceai/go/openai.mdx');
  const guide = integrations.find(item => item.id === 'openai-go');
  assert.equal(guide?.href, '/docs/integrations/traceai/go/openai');
  assert.equal(guide?.category, 'providers');
  assert.equal(guide?.logo, 'openai');
  for (const setting of [
    'Go 1.26 or later', 'openai-go/v3` v3.71.1 or later',
    'github.com/future-agi/traceAI/go/openai@v0.1.0',
    'github.com/openai/openai-go/v3@v3.78.0',
    'go.opentelemetry.io/otel/sdk@v1.47.0',
    'go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0',
    'go mod init example.com/openai-go-example', 'go mod tidy', 'go run . -stream -fail',
  ]) assert.ok(page.includes(setting), setting);
  assert.doesNotMatch(page, /end-to-end test|In our test|MARK_DEFAULT|trace_id=|latest on 20\d\d-/i);
});

test('OpenAI Go usage distinguishes missing counts from API-reported zeros', () => {
  const page = read('src/pages/docs/integrations/traceai/go/openai.mdx');
  const usageRow = page.split('\n').find(line => line.startsWith('| `gen_ai.usage.input_tokens`'));
  assert.ok(usageRow, 'The guide must explain token usage capture');
  assert.match(usageRow, /only when the API returns usage; missing usage is not synthesized as zero/);
  assert.doesNotMatch(page, /never written as (?:0|zero)/i);
});

test('OpenAI Go privacy scopes tool data to input and output channels', () => {
  const page = read('src/pages/docs/integrations/traceai/go/openai.mdx');
  const privacy = page.split('## Privacy\n')[1]?.split('\n## ')[0];
  assert.ok(privacy, 'The guide must explain privacy controls');
  assert.match(privacy, /`FI_HIDE_INPUTS=true` \| `input\.value` becomes `__REDACTED__`; `gen_ai\.input\.messages\.\*`, system instructions, the standalone `gen_ai\.tool\.call\.arguments` attribute and the API error message are dropped/);
  assert.match(privacy, /`FI_HIDE_OUTPUTS=true` \| `output\.value` becomes `__REDACTED__`; `gen_ai\.output\.messages\.\*`, the standalone `gen_ai\.tool\.call\.result` attribute and the API error message are dropped/);
  assert.match(privacy, /Model-generated tool-call arguments are outputs \(`output\.value` and `gen_ai\.output\.messages\.\*`\), so `FI_HIDE_INPUTS=true` alone does not hide them/);
  assert.match(privacy, /Tool results returned to the model are inputs \(`input\.value` and `gen_ai\.input\.messages\.\*`\), so `FI_HIDE_OUTPUTS=true` alone does not hide them/);
  assert.match(privacy, /standalone tool-attribute rules do not remove every copy of tool data/);
  assert.match(privacy, /To hide tool data across a conversation, enable both `FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true`/);
  assert.doesNotMatch(privacy, /input messages, system instructions, tool-call arguments|output messages, tool-call results/);
});

test('OpenAI Go privacy distinguishes granular message filtering from content suppression', () => {
  const page = read('src/pages/docs/integrations/traceai/go/openai.mdx');
  const privacy = page.split('## Privacy\n')[1]?.split('\n## ')[0];
  assert.ok(privacy, 'The guide must explain privacy controls');
  assert.match(privacy, /`FI_HIDE_INPUT_TEXT=true` \| redact text only in `gen_ai\.input\.messages\.\*`/);
  assert.match(privacy, /`FI_HIDE_OUTPUT_TEXT=true` \| redact text only in `gen_ai\.output\.messages\.\*`/);
  assert.match(privacy, /`FI_HIDE_INPUT_IMAGES=true` \| drop image URLs only from `gen_ai\.input\.messages\.\*`/);
  assert.match(privacy, /message, text and image switches alone do not prevent content export/);
  assert.match(privacy, /`input\.value` retains original prompts and image URLs \(including base64 images up to `FI_BASE64_IMAGE_MAX_LENGTH`\), and `output\.value` retains original answers/);
  assert.match(privacy, /set `FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true` before constructing the middleware/);
});

test('Tavily uses the released package and is discoverable through the catalog', () => {
  const page = read('src/pages/docs/integrations/traceai/tavily.mdx');
  const entry = integrations.find(item => item.id === 'tavily');
  assert.equal(entry?.href, '/docs/integrations/traceai/tavily');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI SDK');
  for (const pin of ['traceAI-tavily==0.1.1', 'tavily-python==0.8.5', 'fi-instrumentation-otel==1.2.3']) {
    assert.ok(page.includes(pin), pin);
  }
  assert.match(page, /from traceai_tavily import TavilyInstrumentor/);
  assert.match(page, /TavilyInstrumentor\(\)\.instrument\(tracer_provider=trace_provider\)/);
  assert.match(page, /finally:\s+trace_provider\.force_flush\(\)/);
  assert.match(page, /\*\*Observe\*\*/);
  assert.doesNotMatch(page, /Live vendor verification|local stand-in|stored column|Tested versions|checked live|package is Alpha/i);
});

test('Tavily documents all six operations and research stream completion', () => {
  const page = read('src/pages/docs/integrations/traceai/tavily.mdx');
  for (const method of ['search', 'extract', 'map', 'crawl', 'research', 'get_research']) {
    const kind = method === 'search' ? 'RETRIEVER' : 'TOOL';
    assert.ok(page.includes(`| \`${method}\` | \`tavily.${method}\` | \`${kind}\` |`), method);
  }
  for (const attribute of ['tavily.request_id', 'tavily.result_count', 'tavily.url_count', 'tavily.cancelled', 'tavily.stream.closed']) {
    assert.ok(page.includes(`\`${attribute}\``), attribute);
  }
  assert.match(page, /submission, not the entire background research job/);
  assert.match(page, /`close\(\)`.*`await stream\.aclose\(\)`/);
  assert.match(page, /Early closure ends the span with `ERROR`/);
  assert.match(page, /Stream chunks are not recorded/);
  assert.doesNotMatch(page, /only `search` and `extract`|`crawl`, `map`, `research`.*not traced/);
});

test('Tavily preserves privacy controls and scopes them to its own instrumentation', () => {
  const page = read('src/pages/docs/integrations/traceai/tavily.mdx');
  assert.match(page, /export FI_HIDE_INPUTS=true/);
  assert.match(page, /export FI_HIDE_ERROR_DETAILS=true/);
  assert.match(page, /`__REDACTED__`, omit `gen_ai.retrieval.query` and `tavily.request_id`/);
  assert.match(page, /unless `FI_HIDE_ERROR_DETAILS=false`/);
  assert.match(page, /Transport errors and errors from the other five methods record only the exception type/);
  assert.match(page, /not to separate LangChain, MCP or HTTP-client instrumentation/);
  assert.match(page, /literal key values, not encoded or transformed copies/);
});

test('Replicate documents released packages, provider-first setup and catalog discovery', () => {
  const page = read('src/pages/docs/integrations/traceai/replicate.mdx');
  assert.match(page, /pip install traceAI-replicate==0\.1\.0 fi-instrumentation-otel==1\.2\.3 replicate==1\.0\.7/);
  assert.match(page, /Python 3\.10–3\.13/);
  assert.match(page, /replicate>=1\.0\.0,<2/);
  assert.match(page, /from traceai_replicate import ReplicateInstrumentor/);
  const example = [...page.matchAll(/```python\n([\s\S]*?)```/g)][0]?.[1];
  assert.ok(example);
  assert.ok(example.indexOf('trace_provider = register(') < example.indexOf('ReplicateInstrumentor().instrument('));
  assert.ok(example.indexOf('ReplicateInstrumentor().instrument(') < example.indexOf('replicate.run('));
  assert.match(example, /finally:\n    trace_provider\.shutdown\(\)/);
  assert.doesNotMatch(example, /stream_reload_seconds=/);
  assert.match(page, /Open the `my-replicate-app` Observe project/);
  const entry = integrations.find(i => i.id === 'replicate');
  assert.equal(entry?.href, '/docs/integrations/traceai/replicate');
  assert.equal(entry?.category, 'providers');
  assert.equal(entry?.method, 'traceAI SDK');
});

test('Replicate preserves default-off reads, stream costs, cancellation and lifecycle limits', () => {
  const page = read('src/pages/docs/integrations/traceai/replicate.mdx');
  assert.match(page, /Post-stream reads are off by default \(`stream_reload_seconds=0`\)/);
  assert.match(page, /no final prediction status, `predict_time` or token counts/);
  assert.match(page, /No extra request is made and no package worker thread starts/);
  assert.match(page, /stream_reload_seconds=2/);
  assert.match(page, /All three options accept `0`–`10` seconds and default to `0`/);
  for (const setting of ['stream_reload_seconds', 'stream_flush_wait_seconds', 'stream_shutdown_wait_seconds']) {
    assert.ok(page.includes(`| \`${setting}\` |`), setting);
  }
  assert.match(page, /Each read counts toward \[Replicate's API rate limit\]/);
  assert.match(page, /HTTP 429 and 5xx responses are not retried/);
  assert.match(page, /real request to your client's `base_url`, including a local stub server/);
  assert.match(page, /64 stream spans[\s\S]*64 live reads/);
  assert.match(page, /`uninstrument\(\)` never waits for a read/);
  assert.match(page, /up to 5 seconds for a span the finisher thread is exporting/);
  assert.match(page, /`timeout_millis` does not shorten that wait/);
  assert.match(page, /terminal `canceled` status is recorded with an OK span/);
  assert.match(page, /`ERROR` and `replicate.cancelled=true`/);
  assert.match(page, /Partial output is retained, subject to the privacy settings/);
});

test('Replicate keeps privacy instructions without public verification diaries', () => {
  const page = read('src/pages/docs/integrations/traceai/replicate.mdx');
  for (const setting of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS']) {
    assert.ok(page.includes(`export ${setting}=true`), setting);
  }
  assert.match(page, /Error messages and error status descriptions are removed/);
  assert.match(page, /FI_PII_REDACTION=true/);
  assert.match(page, /never downloaded by the instrumentor/);
  assert.match(page, /a `data:` chunk in text output is preserved unless outputs are hidden/);
  assert.match(page, /Webhook URLs are recorded only as present, not by value/);
  assert.match(page, /not what Replicate receives/);
  assert.doesNotMatch(page, /Live vendor verification|verified live|stand-in|load average|privacy scan|traceAI#219|## Tested versions/i);
});

test('mcp-use guide is discoverable and uses the released callback dependency floor', () => {
  const page = read('src/pages/docs/integrations/traceai/mcp-use.mdx');
  const entry = integrations.find(item => item.id === 'mcp-use');
  assert.equal(entry?.href, '/docs/integrations/traceai/mcp-use');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI callback');
  for (const dependency of ['traceAI-mcp-use==0.1.1', 'mcp-use==1.7.1', 'langchain-openai==1.7.2', 'langchain-core>=1.6.12,<2']) {
    assert.ok(page.includes(dependency), dependency);
  }
  assert.doesNotMatch(page, /langchain-core>=1\.0\.0|Tested with|test suite|verified live|2026-10-16/i);
});

test('mcp-use guide supplies the server it launches and closes sessions and tracing', () => {
  const page = read('src/pages/docs/integrations/traceai/mcp-use.mdx');
  const python = [...page.matchAll(/```python\n([\s\S]*?)\n```/g)].map(match => match[1]);
  const server = python.find(block => block.includes('def add('));
  const agent = python.find(block => block.includes('asyncio.run(main())'));
  assert.ok(server && agent, 'Both executable example files must be provided');
  assert.match(page, /Save this as `calculator_server\.py`/);
  assert.match(page, /Save this as `agent\.py` next to `calculator_server\.py`/);
  assert.match(server, /from mcp\.server\.fastmcp import FastMCP/);
  assert.match(server, /@mcp\.tool\(\)\ndef add\(a: int, b: int\) -> str:/);
  assert.match(server, /return str\(a \+ b\)/);
  assert.match(server, /mcp\.run\("stdio"\)/);
  assert.match(agent, /Path\(__file__\)\.resolve\(\)\.with_name\("calculator_server\.py"\)/);
  assert.match(agent, /"command": sys\.executable, "args": \[server\]/);
  assert.match(agent, /callbacks=\[FutureAGICallback\(tracer_provider=trace_provider\)\]/);
  assert.match(agent, /finally:\n\s+await client\.close_all_sessions\(\)/);
  assert.match(agent, /finally:\n\s+trace_provider\.shutdown\(\)/);
  assert.match(page, /```bash\npython agent\.py\n```/);
  // Syntax-check the two complete application files in CI, without importing packages.
  for (const snippet of [server, agent]) {
    const result = spawnSync('python3', ['-I', '-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: snippet, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }
});

test('mcp-use guide retains actionable privacy and callback coverage limits', () => {
  const page = read('src/pages/docs/integrations/traceai/mcp-use.mdx');
  for (const setting of ['FI_HIDE_INPUTS=true', 'FI_HIDE_OUTPUTS=true', 'MCP_USE_ANONYMIZED_TELEMETRY=false']) {
    assert.ok(page.includes(setting), setting);
  }
  assert.match(page, /console logs are separate from exported spans/);
  assert.match(page, /not a guarantee of detecting arbitrary secrets/);
  assert.match(page, /output_schema[^\n]*does not receive callbacks/);
  assert.match(page, /not TypeScript agents or remote/);
  assert.match(page, /Do not also instrument the same agent/);
  assert.match(page, /Callback spans are not made current/);
});

test('Discovery Engine uses released packages and a standalone v1 search example', () => {
  const page = read('src/pages/docs/integrations/traceai/google-discovery-engine.mdx');
  const catalog = integrations.find(i => i.id === 'google-discovery-engine');
  assert.equal(catalog?.href, '/docs/integrations/traceai/google-discovery-engine');
  assert.equal(catalog?.category, 'frameworks');
  assert.equal(catalog?.method, 'traceAI SDK');
  assert.ok(catalog?.aliases?.includes('Vertex AI Search'));
  for (const dependency of [
    'traceAI-discoveryengine==0.1.1',
    'fi-instrumentation-otel==1.2.3',
    'google-cloud-discoveryengine==0.20.5',
  ]) assert.ok(page.includes(dependency), dependency);
  assert.match(page, /Python 3\.10–3\.13/);
  assert.match(page, /google-cloud-discoveryengine>=0\.20\.5,<1/);
  assert.match(page, /from google\.cloud import discoveryengine_v1 as discoveryengine/);
  const example = page.split('## Run a traced search\n')[1].split('## Trace answers')[0];
  assert.match(example, /DiscoveryEngineInstrumentor\(\)\.instrument\(tracer_provider=trace_provider\)/);
  assert.ok(example.indexOf('register(') < example.indexOf('.instrument('));
  assert.ok(example.indexOf('.instrument(') < example.indexOf('client.search('));
  assert.match(example, /first_page = next\(pager\.pages\)/);
  assert.match(example, /finally:\n    trace_provider\.force_flush\(\)/);
  assert.match(example, /python discoveryengine_example\.py/);
  assert.match(example, /Observe → Traces/);
  assert.doesNotMatch(example, /answers\.answer_query\(/);
});

test('Discovery Engine preserves API prerequisites and privacy limits without a QA diary', () => {
  const page = read('src/pages/docs/integrations/traceai/google-discovery-engine.mdx');
  const setup = page.split('## Run a traced search\n')[0];
  assert.match(setup, /Application Default Credentials/);
  assert.match(setup, /FI_API_KEY/);
  assert.match(setup, /FI_SECRET_KEY/);
  assert.match(setup, /export FI_HIDE_INPUTS=true/);
  assert.match(setup, /export FI_HIDE_ERROR_DETAILS=true/);
  assert.match(page, /Public website search with a Google API key/);
  assert.match(page, /Enterprise edition features and Generative responses/);
  assert.match(page, /Large Language Model add-on/);
  assert.match(page, /Advanced website indexing/);
  assert.match(page, /eu-discoveryengine\.googleapis\.com/);
  assert.match(page, /first page creates no additional spans/);
  assert.match(page, /Only the Python v1 clients/);
  assert.match(page, /reworded or truncated copies/);
  assert.match(page, /custom gRPC channel/);
  assert.match(page, /Serving config and session names remain/);
  assert.doesNotMatch(page, /Live vendor verification|Tested versions|stand-ins|fi_verify|our test|276682b6|2026-10-18/i);
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

test('Voyage AI guide installs the package and keeps customer-facing privacy guidance', () => {
  const page = read('src/pages/docs/integrations/traceai/voyage.mdx');
  const catalog = integrations.find(i => i.id === 'voyage-ai');
  assert.equal(catalog?.href, '/docs/integrations/traceai/voyage');
  assert.equal(catalog?.method, 'traceAI SDK');
  for (const text of [
    'pip install "traceAI-voyage>=0.1.2" "fi-instrumentation-otel>=1.2.3"', 'voyageai>=0.3.7,<1',
    'voyage.multimodal_embed', 'voyage.contextualized_embed', '[media omitted]',
    'VoyageInstrumentor().instrument(tracer_provider=trace_provider)', 'trace_provider.force_flush()',
    'capture_content=True', 'FI_HIDE_INPUTS=true', 'FI_HIDE_OUTPUTS=true',
  ]) assert.ok(page.includes(text), text);
  assert.doesNotMatch(page, /Live vendor verification|verified live|Not yet run live|trace [0-9a-f]{8}-/i);
});

test('Voyage AI privacy guidance requires error suppression and explains explicit overrides', () => {
  const page = read('src/pages/docs/integrations/traceai/voyage.mdx');
  const install = page.split('## 1. Installation')[1].split('## 2.')[0];
  assert.match(install, /```bash\s+pip install "traceAI-voyage>=0\.1\.2" "fi-instrumentation-otel>=1\.2\.3"\s+```/);
  const privacy = page.split('## Privacy')[1].split('## Hosts')[0];
  assert.match(privacy, /Set privacy environment variables before calling `register\(\)` and `instrument\(\)`/);
  assert.match(privacy, /Hides query, texts, documents, scores and error messages; counts, model, tokens and error types remain/);
  assert.match(privacy, /Error-message suppression requires `fi-instrumentation-otel>=1\.2\.3`/);
  assert.match(privacy, /Leave `FI_HIDE_ERROR_DETAILS` unset or set it to `true`/);
  assert.match(privacy, /do not override it with `FI_HIDE_ERROR_DETAILS=false` or `TraceConfig\(hide_error_details=False\)`/);
  assert.match(privacy, /overrides can expose response content in exception messages and `ERROR` status descriptions/);
  assert.doesNotMatch(page, /No content at all|fi-instrumentation-otel>=1\.1\.0/);
});

test('Temporal TypeScript warns about incompatible histories before setup', () => {
  const page = read('src/pages/docs/integrations/frameworks/temporal-typescript.mdx');
  const prerequisites = page.split('## Set up tracing')[0];
  const warning = [...prerequisites.matchAll(/<Warning>([\s\S]*?)<\/Warning>/g)]
    .map(match => match[1]).find(text => text.includes('existing workflow histories'));
  assert.ok(warning, 'Migration warning must appear before installation');
  assert.match(warning, /Do not replace `@temporalio\/interceptors-opentelemetry` with `@temporalio\/interceptors-opentelemetry-v2` in place/);
  assert.match(warning, /non-determinism errors on replay/);
  assert.match(warning, /compatible original-interceptor workers until they complete/);
  assert.match(warning, /Worker Versioning migration that preserves replay compatibility/);
  assert.match(warning, /Use v2 for new executions/);
});

test('Temporal TypeScript runs the server, Worker, and starter in separate terminals', () => {
  const page = read('src/pages/docs/integrations/frameworks/temporal-typescript.mdx');
  const runStep = page.split('<Step title="Run a workflow and inspect its trace">')[1]?.split('</Step>')[0];
  assert.ok(runStep, 'The guide must explain how to run the example');
  assert.deepEqual([...runStep.matchAll(/```bash\n([\s\S]*?)\n```/g)].map(match => match[1].trim()), [
    'temporal server start-dev',
    'npm run worker',
    'npm run start',
  ]);
  assert.match(runStep, /three separate terminals/);
  for (const terminal of ['Terminal 1 — Temporal server', 'Terminal 2 — Worker', 'Terminal 3 — starter']) {
    assert.ok(runStep.includes(terminal), terminal);
  }
  assert.match(runStep, /Set `FI_API_KEY`, `FI_SECRET_KEY`, and `FI_PROJECT_NAME` in both of those terminals/);
  assert.match(runStep, /exports in one terminal do not apply to another/);
  assert.match(runStep, /Wait until it reports `RUNNING`/);
  assert.match(runStep, /stop the Worker with Ctrl\+C/);
});

test('Temporal TypeScript documents and declares the OpenTelemetry Node.js minimum', () => {
  const example = 'examples/frameworks/temporal-typescript/';
  const page = read('src/pages/docs/integrations/frameworks/temporal-typescript.mdx');
  const readme = read(example + 'README.md');
  const manifest = JSON.parse(read(example + 'package.json'));
  const lock = JSON.parse(read(example + 'package-lock.json'));
  for (const text of [page, readme]) {
    assert.match(text, /Node\.js 20\.6\.0 or newer/);
    assert.match(text, /Node\.js 22 is recommended/);
    assert.doesNotMatch(text, /Node\.js 20\.3/);
  }
  assert.equal(manifest.engines.node, '>=20.6.0');
  assert.deepEqual(lock.packages[''].engines, manifest.engines);
  for (const name of Object.keys(manifest.dependencies).filter(name => name.startsWith('@opentelemetry/'))) {
    assert.equal(lock.packages['node_modules/' + name].engines.node, '^18.19.0 || >=20.6.0', name);
  }
});

test('Temporal Go uses the official extension and authenticated traces-only OTLP export', () => {
  const page = read('src/pages/docs/integrations/frameworks/temporal-go.mdx');
  const catalog = integrations.find(i => i.id === 'temporal-go');
  assert.equal(catalog?.method, 'OpenTelemetry');
  for (const term of ['go.temporal.io/sdk/contrib/opentelemetry@v0.8.1', 'v1.46.0', 'otel/exporters/otlp/otlptrace/otlptracehttp@v1.43.0', 'https://api.futureagi.com/tracer/v1/traces', 'X-Api-Key', 'X-Secret-Key', 'project_name', 'NewTracingInterceptor', 'RunActivity', 'provider.Shutdown']) assert.ok(page.includes(term), term);
  assert.doesNotMatch(page, /AddOtlpMetricExporter|AddOtlpLogExporter|traceai-temporal-go|Live vendor verification/);
  assert.match(read('src/pages/docs/integrations/frameworks/temporal.mdx'), /frameworks\/temporal-go/);
});

test('OpenAI Realtime guide installs the published package and runs a complete example', () => {
  const page = read('src/pages/docs/integrations/traceai/openai_realtime.mdx');
  const catalog = integrations.find(i => i.id === 'openai-realtime');
  assert.equal(catalog?.href, '/docs/integrations/traceai/openai_realtime');
  assert.equal(catalog?.category, 'voice');
  assert.match(page, /python -m pip install traceAI-openai-realtime/);
  assert.match(page, /client\.realtime\.connect\(\)/);
  assert.match(page, /traceAI\/blob\/main\/python\/frameworks\/openai-realtime\/examples\/voice_agent\.py/);
  assert.match(page, /does not trace `client\.beta\.realtime`/);
  assert.match(page, /enable input audio transcription/);
  assert.match(page, /python voice_agent\.py --typed/);
  assert.match(page, /FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true/);
  assert.match(page, /developers\.openai\.com\/api\/docs\/guides\/realtime/);
  assert.doesNotMatch(publicProse(page), /Live vendor verification|trace id|stand-in|QA harness/i);
});

test('Microsoft Agent Framework guide uses the released package and global provider without a test diary', () => {
  const page = read('src/pages/docs/integrations/traceai/microsoft-agent-framework.mdx');
  const catalog = integrations.find(i => i.id === 'microsoft-agent-framework');
  assert.equal(catalog?.href, '/docs/integrations/traceai/microsoft-agent-framework');
  assert.equal(catalog?.category, 'frameworks');
  assert.match(page, /pip install "traceAI-agent-framework==0\.1\.0" agent-framework/);
  assert.match(page, /Python 3\.10 to 3\.13 and Agent Framework 1\.0\.0 or later/);
  for (const term of ['set_global_tracer_provider=True', 'enable_instrumentation(enable_sensitive_data=True)', 'enable_fi_attribute_mapping()', 'trace_provider.force_flush()', 'agent_framework.usage.*', 'configure_otel_providers()']) assert.ok(page.includes(term), term);
  assert.doesNotMatch(page, /Tested versions|end to end|unit tests|unique marker|Verified|\b20\d\d-\d\d-\d\d\b/);
});
