import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = name => readFileSync(new URL(name, import.meta.url), 'utf8');
const guide = read('../src/pages/docs/integrations/traceai/spring-boot.mdx');
const pom = read('../public/examples/spring-ai/pom.xml');
const java = [...guide.matchAll(/```java\n([\s\S]*?)\n```/g)].map(m => m[1]).join('\n');

test('the published dependency and native setup agree; no second tracing pipeline', () => {
  const version = guide.match(/com\.futureagi:traceai-spring-ai:([\d.]+)/)?.[1];
  assert.ok(version && version !== '1.0.0');
  assert.equal(pom.match(/<artifactId>traceai-spring-ai<\/artifactId>\s*<version>([^<]+)/)?.[1], version);
  assert.match(java, /new SpringAIObservationFilter\(\)/);
  assert.match(java, /new SpringAITracingObservationHandler\(tracer\)/);
  assert.match(java, /new SpringAIToolExecutionExceptionProcessor\(registry, existingProcessor\)/);
  assert.doesNotMatch(java + pom, /TracedChatModel|TracedEmbeddingModel|TraceAI\.init|traceai-spring-boot-starter|main-SNAPSHOT/);
});

test('both Boot export configurations supply keys and project attribution', () => {
  for (const prefix of ['management.otlp.tracing', 'management.opentelemetry.tracing.export.otlp']) {
    for (const [key, env] of [['X-Api-Key', 'FI_API_KEY'], ['X-Secret-Key', 'FI_SECRET_KEY'], ['fi-project-name', 'FI_PROJECT_NAME']]) {
      assert.ok(guide.includes(`${prefix}.headers.${key}=\${${env}}`));
    }
    assert.ok(guide.includes(`${prefix}.endpoint=`));
  }
  assert.ok(guide.includes('management.opentelemetry.resource-attributes.project_name=${FI_PROJECT_NAME}'));
});

test('the old M4 artifact is distinguished from modern runtimes and privacy remains explicit', () => {
  assert.match(guide, /NoSuchMethodError/);
  assert.match(guide, /Message\.getContent\(\)/);
  assert.match(guide, /1\.0\.0-M4/);
  assert.doesNotMatch(guide, /M4\s*\+/);
  assert.match(guide, /FI_HIDE_ERROR_DETAILS=true/);
  assert.match(guide, /32,000 characters/);
  for (const url of ['https://docs.spring.io/spring-ai/reference/1.1/observability/index.html',
    'https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html']) {
    assert.ok(guide.includes(`](${url})`));
  }
});
