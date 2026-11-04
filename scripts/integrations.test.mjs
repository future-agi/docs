import './ollama-java.test.mjs';
import './azure-openai-java.test.mjs';
import './langsmith-page.test.mjs';
import './vercel-platform-page.test.mjs';
import './scalekit-page.test.mjs';
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

test('public prose and catalog labels contain no internal QA label or Alpha release status', () => {
  for (const file of routeFiles.filter(f=>f.endsWith('.mdx'))) {
    const prose=publicProse(fs.readFileSync(file,'utf8'));
    assert.doesNotMatch(prose,/\bnot\s+tested\b/i,file);
    assert.doesNotMatch(prose,/\balpha\b/i,file);
  }
  for (const item of [...integrations,...integrationCategories,...integrationAids]) assert.doesNotMatch(JSON.stringify(item),/\bnot\s+tested\b|\balpha\b/i);
  assert.equal(publicProse('Beta. `pkg==1.0.0-alpha`\n```python\nmodel="alpha"\n```\n'),'Beta. \n\n');
});

test('Temporal Go uses the official extension and authenticated traces-only OTLP export', () => {
  const page = read('src/pages/docs/integrations/frameworks/temporal-go.mdx');
  const catalog = integrations.find(i => i.id === 'temporal-go');
  assert.equal(catalog?.method, 'OpenTelemetry');
  for (const term of ['go.temporal.io/sdk/contrib/opentelemetry@v0.8.1', 'v1.46.0', 'otel/exporters/otlp/otlptrace/otlptracehttp@v1.43.0', 'https://api.futureagi.com/tracer/v1/traces', 'X-Api-Key', 'X-Secret-Key', 'project_name', 'NewTracingInterceptor', 'RunActivity', 'provider.Shutdown']) assert.ok(page.includes(term), term);
  assert.doesNotMatch(page, /AddOtlpMetricExporter|AddOtlpLogExporter|traceai-temporal-go|Live vendor verification/);
  assert.match(read('src/pages/docs/integrations/frameworks/temporal.mdx'), /frameworks\/temporal-go/);
});
