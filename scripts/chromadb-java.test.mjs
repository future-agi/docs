import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/java/vector-databases.mdx', import.meta.url), 'utf8');
const chroma = page.split('## ChromaDB\n')[1]?.split('\n## Weaviate')[0];

test('Chroma Java uses released Central coordinates and declares the provided client', () => {
  assert.ok(chroma, 'ChromaDB section exists');
  for (const artifact of ['traceai-java-core', 'traceai-java-chromadb']) {
    assert.match(chroma, new RegExp(`<groupId>com\\.futureagi</groupId>\\s*<artifactId>${artifact}</artifactId>\\s*<version>1\\.0\\.0</version>`));
    assert.ok(chroma.includes(`com.futureagi:${artifact}:1.0.0`));
  }
  assert.match(chroma, /<groupId>io\.github\.amikos-tech<\/groupId>\s*<artifactId>chromadb-java-client<\/artifactId>\s*<version>0\.1\.7<\/version>/);
  assert.ok(chroma.includes('io.github.amikos-tech:chromadb-java-client:0.1.7'));
  assert.ok(chroma.includes('mavenCentral()'));
  assert.doesNotMatch(chroma, /main-SNAPSHOT|com\.github\.future-agi\.traceAI/);
});

test('Chroma Java bounds compatibility before installation without recommending a downgrade', () => {
  const warning = chroma.match(/<Warning>([\s\S]*?)<\/Warning>/)?.[1];
  assert.ok(warning);
  assert.match(warning, /\/api\/v1/);
  assert.match(warning, /1\.5\.9/);
  assert.match(warning, /HTTP 410/);
  assert.match(warning, /Do not downgrade/);
  assert.ok(chroma.indexOf('<Warning>') < chroma.indexOf('```xml'));
  assert.doesNotMatch(chroma, /main-SNAPSHOT|0\.2\.0|traced\.updateEmbeddings/);
});

test('Chroma Java query example has imports and uses the existing collection', () => {
  assert.match(chroma, /import java\.util\.List;/);
  assert.match(chroma, /import tech\.amikos\.chromadb\.model\.QueryEmbedding\.IncludeEnum;/);
  assert.match(chroma, /new TracedChromaCollection\(collection, collection\.getName\(\)\)/);
  assert.match(chroma, /embedding function/);
  assert.doesNotMatch(chroma, /\/\* get from ChromaDB client \*\//);
});
