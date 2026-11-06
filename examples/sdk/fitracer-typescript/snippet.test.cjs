const assert = require('node:assert/strict');
const { mkdtempSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const http = require('node:http');
const { join, resolve } = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');
const { test } = require('node:test');
const ts = require('typescript');
const { context, trace } = require('@opentelemetry/api');
const { setSession, setUser, setMetadata, setTags } = require('@traceai/fi-core');

const page = resolve(__dirname, '../../../src/pages/docs/sdk/tracing/fitracer.mdx');
const attrs = (entries = []) => Object.fromEntries(entries.map(({ key, value }) => [
  key, value.stringValue ?? value.arrayValue?.values.map(v => v.stringValue),
]));

// No vendor calls or credentials: the published exporter sends real OTLP to loopback.
// Run under the OS network sandbox in addition to this test-only endpoint configuration.
test('TypeScript guide exports contextual, private, completed spans', async (t) => {
  const tab = readFileSync(page, 'utf8').split('<Tab title="TypeScript">')[1].split('</Tab>')[0];
  const blocks = [...tab.matchAll(/```typescript\n([\s\S]*?)```/g)];
  assert.equal(blocks.length, 1, 'test the complete customer-facing example');
  const source = blocks[0][1].replace(/^    /gm, '');
  assert.equal(source.match(/void main\(\);/g)?.length, 1);

  const temp = mkdtempSync(join(__dirname, '.snippet-'));
  t.after(() => rmSync(temp, { recursive: true, force: true }));
  const filename = join(temp, 'example.ts');
  writeFileSync(filename, source);
  const options = {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.Node16,
    moduleResolution: ts.ModuleResolutionKind.Node16,
    strict: true,
    skipLibCheck: true,
    noEmit: true,
    types: ['node'],
  };
  const program = ts.createProgram([filename], options);
  const diagnostics = ts.getPreEmitDiagnostics(program);
  assert.equal(diagnostics.length, 0, ts.formatDiagnostics(diagnostics, {
    getCurrentDirectory: () => __dirname,
    getCanonicalFileName: f => f,
    getNewLine: () => '\n',
  }));

  const requests = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      requests.push({ path: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end('{}');
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  // Do not consume ambient credentials, privacy flags, or OTLP endpoints.
  const saved = {};
  for (const key of Object.keys(process.env)) {
    if (/^(FI_|OTEL_)/.test(key)) {
      saved[key] = process.env[key];
      delete process.env[key];
    }
  }
  process.env.FI_BASE_URL = `http://127.0.0.1:${server.address().port}`;
  process.env.FI_API_KEY = 'synthetic-api-key';
  process.env.FI_SECRET_KEY = 'synthetic-secret-key';
  t.after(() => {
    for (const key of Object.keys(process.env)) if (/^(FI_|OTEL_)/.test(key)) delete process.env[key];
    Object.assign(process.env, saved);
  });

  // Keep the snippet intact, except expose its entry point rather than auto-running it.
  const loadable = source.replace('void main();', 'export { main, getPolicy, provider, tracer, contextManager };');
  const compiled = ts.transpileModule(loadable, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const executable = join(temp, 'example.cjs');
  writeFileSync(executable, compiled);
  const { main, getPolicy, provider, tracer, contextManager } = require(executable);
  t.after(async () => {
    await provider.shutdown();
    contextManager.disable();
    context.disable();
    trace.disable();
  });

  function wireSpans() {
    return requests.flatMap(request => {
      assert.equal(request.path, '/tracer/v1/traces');
      assert.match(request.headers['content-type'], /application\/json/);
      assert.equal(request.headers['x-api-key'], 'synthetic-api-key');
      assert.equal(request.headers['x-secret-key'], 'synthetic-secret-key');
      return JSON.parse(request.body).resourceSpans.flatMap(resource => {
        assert.equal(attrs(resource.resource.attributes).project_name, 'my-project');
        return resource.scopeSpans.flatMap(scope => scope.spans);
      });
    });
  }
  function requestContext(id) {
    return setUser(setSession(context.active(), { sessionId: `sess-${id}` }), { userId: `user-${id}` });
  }

  await t.test('old raw-tracer pattern loses attributes, bypasses privacy, and leaks unfinished work', async () => {
    const raw = provider.getTracer('old-guide');
    context.with(requestContext('raw'), () => {
      raw.startActiveSpan('old-success', span => {
        span.setAttribute('input.value', 'synthetic private input');
        span.end();
      });
      assert.throws(() => raw.startActiveSpan('old-error', () => {
        throw new Error('synthetic failure before span.end');
      }), /synthetic failure/);
    });
    await provider.forceFlush();
    const spans = wireSpans();
    assert.equal(spans.length, 1);
    assert.equal(attrs(spans[0].attributes)['session.id'], undefined);
    assert.equal(attrs(spans[0].attributes)['user.id'], undefined);
    assert.equal(attrs(spans[0].attributes)['input.value'], 'synthetic private input');
  });

  await t.test('concurrent async requests preserve parentage and isolate context', async () => {
    const start = wireSpans().length;
    await Promise.all(['a', 'b'].map(id => context.with(
      setTags(setMetadata(requestContext(id), { route: 'policies' }), ['custom']),
      () => tracer.startActiveSpan(`request-${id}`, async parent => {
        try {
          await delay(5);
          assert.equal(trace.getActiveSpan().spanContext().spanId, parent.spanContext().spanId);
          assert.equal(await getPolicy('returns'), 'Returns are accepted within 30 days.');
        } finally {
          parent.end();
        }
      }),
    )));
    await provider.forceFlush();
    const spans = wireSpans().slice(start);
    assert.equal(spans.length, 4, 'one parent and one child per request, no duplicate spans');
    for (const id of ['a', 'b']) {
      const parent = spans.find(span => span.name === `request-${id}`);
      const child = spans.find(span => span.name === 'get-policy' && span.traceId === parent.traceId);
      assert.equal(child.parentSpanId, parent.spanId);
      assert.equal(child.status.code, 1);
      assert.ok(BigInt(child.endTimeUnixNano) >= BigInt(child.startTimeUnixNano));
      const attributes = attrs(child.attributes);
      assert.equal(attributes['session.id'], `sess-${id}`);
      assert.equal(attributes['user.id'], `user-${id}`);
      assert.equal(attributes['gen_ai.span.kind'], 'TOOL');
      assert.equal(attributes['input.value'], '__REDACTED__');
      assert.equal(attributes['output.value'], '__REDACTED__');
      assert.equal(attributes.metadata, JSON.stringify({ route: 'policies' }));
      assert.deepEqual(JSON.parse(attributes['tag.tags']), ['custom']);
    }
    assert.notEqual(spans.find(s => s.name === 'request-a').traceId, spans.find(s => s.name === 'request-b').traceId);
    assert.equal(trace.getActiveSpan(), undefined);
  });

  await t.test('failed awaited work is rethrown and exports one private error span', async () => {
    const start = wireSpans().length;
    await assert.rejects(context.with(requestContext('error'), () => getPolicy('unknown')), /Unknown policy topic/);
    await provider.forceFlush();
    const spans = wireSpans().slice(start);
    assert.equal(spans.length, 1);
    const span = spans[0];
    assert.equal(span.name, 'get-policy');
    assert.equal(span.status.code, 2);
    assert.ok(!span.status.message);
    assert.equal(attrs(span.attributes)['error.type'], 'Error');
    assert.equal(attrs(span.attributes)['session.id'], 'sess-error');
    assert.equal(attrs(span.attributes)['input.value'], '__REDACTED__');
    assert.equal(span.events.length, 1);
    assert.equal(span.events[0].name, 'exception');
    assert.deepEqual(attrs(span.events[0].attributes), { 'exception.type': 'Error' });
    assert.ok(!JSON.stringify(span).includes('Unknown policy topic'));
    assert.ok(BigInt(span.endTimeUnixNano) > 0n);
  });

  await t.test('the full documented entry point flushes before exit', async () => {
    const start = wireSpans().length;
    await main();
    const spans = wireSpans().slice(start);
    assert.equal(spans.length, 1);
    assert.equal(attrs(spans[0].attributes)['session.id'], 'sess-123');
    assert.equal(attrs(spans[0].attributes)['user.id'], 'user-456');
  });
});
