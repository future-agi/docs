import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/java/llm-providers.mdx', import.meta.url), 'utf8');
const azure = page.split('## Azure OpenAI\n')[1]?.split('\n## ')[0];

test('Azure Java setup uses released coordinates and declares the provided Azure SDK', () => {
  assert.ok(azure, 'Azure OpenAI section exists');
  assert.match(azure, /<groupId>com\.futureagi<\/groupId>\s*<artifactId>traceai-java-azure-openai<\/artifactId>\s*<version>1\.0\.0<\/version>/);
  assert.match(azure, /com\.futureagi:traceai-java-azure-openai:1\.0\.0/);
  assert.match(azure, /<groupId>com\.azure<\/groupId>\s*<artifactId>azure-ai-openai<\/artifactId>\s*<version>1\.0\.0-beta\.16<\/version>/);
  assert.match(azure, /com\.azure:azure-ai-openai:1\.0\.0-beta\.16/);
  assert.doesNotMatch(azure, /main-SNAPSHOT|com\.github\.future-agi/);
});

test('Azure Java scope distinguishes blocking calls, unwrap, and upstream migration', () => {
  assert.match(azure, /synchronous|blocking/);
  assert.match(azure, /streaming/);
  assert.match(azure, /OpenAIAsyncClient/);
  assert.match(azure, /unwrap\(\)/);
  assert.match(azure, /not (?:traced|instrumented|a drop-in)/);
  assert.match(azure, /github\.com\/Azure\/azure-sdk-for-java/);
  assert.match(azure, /AZURE_OPENAI_DEPLOYMENT/);
  assert.match(azure, /TraceAI\.shutdown\(\)/);
  assert.doesNotMatch(azure, /all API calls|handles all message types/);
});
