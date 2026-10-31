import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/java/llm-providers.mdx', import.meta.url), 'utf8');
const section = page.split('## Ollama\n')[1]?.split('\n## IBM Watsonx')[0];

test('Ollama Java installs the released wrapper and its explicit legacy SDK dependency', () => {
  assert.ok(section);
  assert.match(section, /<groupId>com\.futureagi<\/groupId>\s*<artifactId>traceai-java-ollama<\/artifactId>\s*<version>1\.0\.0<\/version>/);
  assert.match(section, /<groupId>io\.github\.ollama4j<\/groupId>\s*<artifactId>ollama4j<\/artifactId>\s*<version>1\.0\.79<\/version>/);
  assert.match(section, /com\.futureagi:traceai-java-ollama:1\.0\.0/);
  assert.match(section, /io\.github\.ollama4j:ollama4j:1\.0\.79/);
  assert.doesNotMatch(section, /main-SNAPSHOT|com\.github\.future-agi/);
});

test('Ollama Java states the SDK boundary and uses working released chat with shutdown', () => {
  assert.match(section, /1\.1\.7/);
  assert.match(section, /not compatible/);
  assert.match(section, /provided/);
  assert.match(section, /traced\.chat\(/);
  assert.match(section, /finally\s*\{\s*TraceAI\.shutdown\(\)/);
  assert.doesNotMatch(section, /traced\.generate\(/);
  assert.match(section, /`generate\(\)`.*1\.0\.0/);
});

test('Ollama Java does not promise unsupported streaming, tools or usage', () => {
  assert.match(section, /[Ss]treaming callbacks/);
  assert.match(section, /tool-call attributes/);
  assert.match(section, /token usage/);
  assert.match(section, /unwrap\(\)/);
  assert.match(section, /client-side/);
  assert.doesNotMatch(section, /server's own timing/);
});
