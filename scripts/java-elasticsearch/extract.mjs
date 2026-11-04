import assert from 'node:assert/strict';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';

const page = readFileSync(new URL('../../src/pages/docs/integrations/traceai/java/vector-databases.mdx', import.meta.url), 'utf8');
const section = page.split('## Elasticsearch\n')[1].split('## Common span attributes')[0];
const native = section.split('### Optional retrieval metadata')[0];
assert.match(native, /new OpenTelemetryForElasticsearch\(sdk, false\)/);
assert.match(native, /"project_name"/);
assert.match(native, /"project_type", "observe"/);
assert.match(native, /"X-Api-Key"/);
assert.match(native, /"X-Secret-Key"/);
assert.match(native, /\/tracer\/v1\/traces/);
assert.doesNotMatch(section, /main-SNAPSHOT|com\.github\.future-agi/);
assert.match(section, /com\.futureagi:traceai-java-elasticsearch:1\.0\.1/);
assert.match(section, /RETRIEVER.*parent.*native database child/);

const output = new URL('./target/generated-sources/', import.meta.url);
mkdirSync(output, { recursive: true });
function snippet(name) {
  const code = section.split(`\x60\x60\x60java ${name}\n`)[1]?.split('\x60\x60\x60')[0];
  assert.ok(code, `Missing executable snippet: ${name}`);
  return code;
}
const main = snippet('NativeElasticsearchExample.java');
writeFileSync(new URL('NativeElasticsearchExample.java', output), main);
const imports = main.split('\n').filter(line => line.startsWith('import ')).join('\n');
writeFileSync(new URL('OptionalRetrieval.java', output), `${imports}
public class OptionalRetrieval {
    public static void run(ElasticsearchClient client, OpenTelemetrySdk sdk) throws Exception {
${snippet('OptionalRetrieval.java')}
    }
}
`);
writeFileSync(new URL('AsyncSearch.java', output), `${imports}
public class AsyncSearch {
    public static void run(RestClientTransport transport) throws Exception {
${snippet('AsyncSearch.java')}
    }
}
`);
// Build the native example separately with only the dependencies from the page.
// This prevents the optional wrapper or test libraries from masking missing dependencies.
const consumer = new URL('./target/native-consumer/', import.meta.url);
mkdirSync(new URL('src/main/java/', consumer), { recursive: true });
writeFileSync(new URL('src/main/java/NativeElasticsearchExample.java', consumer), main);
const searchBlock = /var client = new ElasticsearchClient\(transport\);[\s\S]*?System\.out\.println\("Matches returned: " \+ response\.hits\(\)\.hits\(\)\.size\(\)\);/;
assert.match(main, searchBlock);
const asyncMain = main.replace('class NativeElasticsearchExample', 'class AsyncElasticsearchExample')
  .replace(searchBlock, snippet('AsyncSearch.java'));
writeFileSync(new URL('src/main/java/AsyncElasticsearchExample.java', consumer), asyncMain);
const knnMain = main.replace('class NativeElasticsearchExample', 'class KnnElasticsearchExample')
  .replace(searchBlock, snippet('NativeKnnSearch.java'));
writeFileSync(new URL('src/main/java/KnnElasticsearchExample.java', consumer), knnMain);
const optionalMain = main.replace('class NativeElasticsearchExample', 'class OptionalElasticsearchExample')
  .replace(searchBlock, 'var client = new ElasticsearchClient(transport);\n' + snippet('OptionalRetrieval.java'));
writeFileSync(new URL('OptionalElasticsearchExample.java', output), optionalMain);
const dependencies = native.split('\x60\x60\x60xml\n')[1].split('\x60\x60\x60')[0];
writeFileSync(new URL('pom.xml', consumer), `
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.futureagi.docs</groupId>
  <artifactId>native-consumer</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <elasticsearch.version>8.12.0</elasticsearch.version>
  </properties>
  <dependencies>${dependencies.replaceAll('<version>8.12.0</version>', '<version>${elasticsearch.version}</version>')}</dependencies>
  <build><plugins>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-compiler-plugin</artifactId><version>3.12.1</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-dependency-plugin</artifactId><version>3.8.1</version></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-jar-plugin</artifactId><version>3.3.0</version></plugin>
  </plugins></build>
</project>
`);
assert.match(section, /not binary-compatible with the 9\.x KNN API/);
console.log('Elasticsearch page contract and snippet extraction passed.');
