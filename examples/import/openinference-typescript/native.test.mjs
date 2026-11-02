import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, before, test } from 'node:test';

const root = fileURLToPath(new URL('.', import.meta.url));
const page = await readFile(new URL('../../../src/pages/docs/integrations/import/openinference.mdx', import.meta.url), 'utf8');
const tab = page.split('<Tab title="TypeScript">')[1]?.split('</Tab>')[0] ?? '';
const source = tab.match(/```typescript\n([\s\S]*?)```/)?.[1];
assert.ok(source, 'The TypeScript example must be extracted from the customer page');
let directory;

// Do not pass developer credentials, tracing settings or NODE_OPTIONS to the app.
function cleanEnv(extra = {}) {
  return { PATH: process.env.PATH, SYSTEMROOT: process.env.SYSTEMROOT, ...extra };
}

function execute(command, args, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: root, env: cleanEnv(env), stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => { stderr += data; });
    const timer = setTimeout(() => { child.kill('SIGKILL'); reject(new Error('Example timed out')); }, 30_000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('close', code => { clearTimeout(timer); resolve({ code, stdout, stderr }); });
  });
}

before(async () => {
  directory = await mkdtemp(join(root, '.native-'));
  await writeFile(join(directory, 'app.mts'), source);
  // Exercise upstream wrapper error behavior without adding a failing example to the guide.
  const failing = source.replace('return location === "rooftop" ? this.plant : "mint";',
    'throw new Error("synthetic-tool-error");');
  assert.notEqual(failing, source, 'Error fixture must replace the documented tool body');
  await writeFile(join(directory, 'error.mts'), failing);
  const config = tab.match(/```json\n([\s\S]*?)```/)?.[1];
  assert.ok(config, 'Compile with the exact documented tsconfig');
  await writeFile(join(directory, 'tsconfig.json'), config);
  const result = await execute(join(root, 'node_modules/.bin/tsc'), ['-p', directory]);
  assert.equal(result.code, 0, `Snippet must compile without skipLibCheck: ${result.stdout}\n${result.stderr}`);
});
after(async () => { if (directory) await rm(directory, { recursive: true, force: true }); });

function attributes(entries = []) {
  return Object.fromEntries(entries.map(({ key, value }) => [key, value.stringValue ?? value.intValue ?? value.boolValue]));
}

async function capture(t, { filename = 'app', hidden = false, configured = true } = {}) {
  const requests = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    requests.push({ path: req.url, headers: req.headers, method: req.method, body: Buffer.concat(chunks).toString('utf8') });
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{}');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  const env = configured ? {
    FI_BASE_URL: `http://127.0.0.1:${server.address().port}/tracer/`,
    FI_API_KEY: 'synthetic-api-key', FI_SECRET_KEY: 'synthetic-secret-key',
  } : {};
  if (hidden) {
    env.OPENINFERENCE_HIDE_INPUTS = 'true';
    env.OPENINFERENCE_HIDE_OUTPUTS = 'true';
  }
  const result = await execute(process.execPath, [join(directory, 'dist', `${filename}.mjs`)], env);
  const spans = [];
  for (const request of requests) {
    assert.equal(request.method, 'POST');
    assert.equal(request.path, '/tracer/v1/traces');
    assert.equal(request.headers['x-api-key'], 'synthetic-api-key');
    assert.equal(request.headers['x-secret-key'], 'synthetic-secret-key');
    assert.match(request.headers['content-type'], /application\/json/);
    const payload = JSON.parse(request.body);
    for (const resourceSpans of payload.resourceSpans) {
      const resource = attributes(resourceSpans.resource.attributes);
      assert.equal(resource.project_name, 'my-openinference-project');
      assert.equal(resource.project_type, 'observe');
      assert.equal(resource['service.name'], 'garden-planner');
      for (const scope of resourceSpans.scopeSpans) spans.push(...scope.spans);
    }
  }
  return { ...result, requests, spans };
}

function assertTree(spans, status) {
  assert.equal(spans.length, 2, 'One agent and one tool, without duplicate instrumentation');
  const agent = spans.find(span => span.name === 'garden-planner');
  const tool = spans.find(span => span.name === 'choose-plant');
  assert.ok(agent);
  assert.ok(tool);
  assert.equal(attributes(agent.attributes)['openinference.span.kind'], 'AGENT');
  assert.equal(attributes(tool.attributes)['openinference.span.kind'], 'TOOL');
  assert.equal(tool.traceId, agent.traceId);
  assert.equal(tool.parentSpanId, agent.spanId);
  assert.ok(!agent.parentSpanId || /^0+$/.test(agent.parentSpanId));
  for (const span of spans) {
    assert.equal(span.status.code, status);
    assert.ok(BigInt(span.endTimeUnixNano) >= BigInt(span.startTimeUnixNano));
  }
  return { agent, tool };
}

test('the exact documented snippet compiles and exports a native agent/tool tree', async t => {
  const result = await capture(t);
  assert.equal(result.code, 0, result.stderr);
  assert.equal(result.stdout.trim(), 'Plant rosemary in your rooftop garden.');
  const { agent, tool } = assertTree(result.spans, 1);
  assert.ok(attributes(agent.attributes)['input.value'].includes('rooftop'));
  assert.ok(attributes(tool.attributes)['input.value'].includes('rooftop'));
  assert.equal(attributes(agent.attributes)['output.value'], 'Plant rosemary in your rooftop garden.');
  assert.equal(attributes(tool.attributes)['output.value'], 'rosemary');
});

test('native input/output privacy switches redact the wire payload', async t => {
  const result = await capture(t, { hidden: true });
  assert.equal(result.code, 0, result.stderr);
  assertTree(result.spans, 1);
  for (const span of result.spans) {
    const attrs = attributes(span.attributes);
    assert.equal(attrs['input.value'], '__REDACTED__');
    assert.equal(attrs['output.value'], '__REDACTED__');
  }
  for (const request of result.requests) assert.doesNotMatch(request.body, /rooftop|rosemary/);
});

test('rejected tool calls propagate ERROR and still flush both spans', async t => {
  const result = await capture(t, { filename: 'error', hidden: true });
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /synthetic-tool-error/);
  assertTree(result.spans, 2);
  for (const span of result.spans) {
    assert.equal(attributes(span.attributes)['input.value'], '__REDACTED__');
    assert.equal(span.status.message, 'synthetic-tool-error');
    const exception = span.events.find(event => event.name === 'exception');
    assert.ok(exception, 'Privacy documentation must not promise exception redaction');
    assert.equal(attributes(exception.attributes)['exception.message'], 'synthetic-tool-error');
    assert.match(attributes(exception.attributes)['exception.stacktrace'], /synthetic-tool-error/);
  }
});

test('missing credentials stop the example before exporting', async t => {
  const result = await capture(t, { configured: false });
  assert.notEqual(result.code, 0);
  assert.match(result.stderr, /Set FI_BASE_URL, FI_API_KEY and FI_SECRET_KEY/);
  assert.equal(result.requests.length, 0);
});
