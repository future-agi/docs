import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/java/llm-providers.mdx', import.meta.url), 'utf8');
const azure = page.split('## Azure OpenAI\n')[1]?.split('\n## ')[0];
const azureAttributes = page.split('### Azure OpenAI attributes\n')[1]?.split('\n### ')[0];

test('Azure Java reference uses released keys and scopes legacy attributes separately', () => {
  assert.ok(azureAttributes, 'Azure has a version-scoped attribute reference');
  const keys = [...azureAttributes.matchAll(/^\| `([^`]+)` \|/gm)].map(match => match[1]);
  assert.deepEqual(keys, [
    'gen_ai.provider.name', 'gen_ai.request.model', 'gen_ai.response.model',
    'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens', 'gen_ai.usage.total_tokens',
    'gen_ai.input.messages', 'gen_ai.output.messages', 'output.value',
  ]);
  assert.match(azureAttributes, /traceai-java-azure-openai:1\.0\.0/);
  assert.match(azure, /\(#azure-openai-attributes\)/);
  const legacy = page.split('### Legacy snapshot provider attributes\n')[1];
  assert.ok(legacy);
  assert.match(legacy, /not the released Azure OpenAI setup/);
  assert.doesNotMatch(azureAttributes, /`llm\./);
});

test('Azure raw payload fields do not promise JSON or replay support', () => {
  assert.ok(azureAttributes);
  assert.match(azureAttributes, /`fi\.raw_input` and `fi\.raw_output` can contain Java object strings/);
  assert.match(azureAttributes, /not full request\/response JSON/);
  assert.match(azureAttributes, /structured message, model, and usage fields/);
  assert.match(azureAttributes, /Do not rely on the raw fields for payload replay/);
  assert.doesNotMatch(page, /Full request\/response as JSON/);
});

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
