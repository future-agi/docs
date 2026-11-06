import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SpanStatusCode } from '@opentelemetry/api';
import { startFakeResponses } from './fake-responses.mjs';
import { runAgent, everything, MARKER } from './helpers.mjs';
import { buildTracerProvider } from '../futureagi-tracing.mjs';

let server;
before(async () => (server = await startFakeResponses()));
after(() => server.close());

const byName = (spans, prefix) => spans.filter((s) => s.name.startsWith(prefix));

test('upstream guard: @openrouter/agent 0.11.0 contains no OpenTelemetry code', () => {
  const root = fileURLToPath(new URL('../node_modules/@openrouter/agent/', import.meta.url));
  const pkg = JSON.parse(fs.readFileSync(`${root}package.json`, 'utf8'));
  assert.equal(pkg.version, '0.11.0');
  const walk = (dir) =>
    fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(`${dir}${e.name}/`) : [`${dir}${e.name}`]));
  const hits = walk(`${root}esm/`).filter((f) => /\.(js|d\.ts)$/.test(f) && /opentelemetry/i.test(fs.readFileSync(f, 'utf8')));
  assert.deepEqual(hits, []);
});

test('a two-turn tool loop is one trace: agent span, two model calls, one tool', async () => {
  const { spans, text, error } = await runAgent(server);
  assert.equal(error, undefined);
  assert.match(text, /sunny/);
  assert.equal(new Set(spans.map((s) => s.spanContext().traceId)).size, 1);
  const [root] = byName(spans, 'invoke_agent');
  assert.equal(root.attributes['fi.span.kind'], 'AGENT');
  assert.equal(root.parentSpanContext, undefined);
  assert.equal(root.attributes['openrouter.agent.model_calls'], 2);
  assert.equal(root.status.code, SpanStatusCode.UNSET);
  const chats = byName(spans, 'chat ');
  const tools = byName(spans, 'execute_tool ');
  assert.equal(chats.length, 2);
  assert.equal(tools.length, 1);
  for (const child of [...chats, ...tools]) assert.equal(child.parentSpanContext.spanId, root.spanContext().spanId);
  assert.deepEqual(chats.map((s) => s.attributes['openrouter.agent.turn_type']), ['initial', 'tool_round']);
  assert.equal(tools[0].attributes['gen_ai.tool.name'], 'get_weather');
  assert.equal(tools[0].attributes['gen_ai.operation.name'], 'execute_tool');
  assert.equal(chats[0].attributes['gen_ai.operation.name'], 'chat');
  assert.equal(chats[0].attributes['gen_ai.request.model'], 'gpt-5.6-terra');
});

test('tokens are on the chat spans once and never on the agent span', async () => {
  const { spans } = await runAgent(server);
  const [root] = byName(spans, 'invoke_agent');
  assert.equal(root.attributes['gen_ai.usage.input_tokens'], undefined);
  const chats = byName(spans, 'chat ');
  for (const chat of chats) {
    assert.ok(chat.attributes['gen_ai.usage.input_tokens'] > 0);
    assert.ok(chat.attributes['gen_ai.usage.output_tokens'] > 0);
  }
});

test('the resource carries project_name', async () => {
  const { spans } = await runAgent(server);
  assert.equal(spans[0].resource.attributes.project_name, 'unit');
  assert.equal(spans[0].resource.attributes.project_type, 'observe');
});

test('default: the prompt, tool arguments, tool result and key leave nothing behind', async () => {
  const { spans } = await runAgent(server);
  const all = everything(spans);
  for (const secret of [MARKER, 'Lisbon', 'sk-or-FAKE-KEY-0001', 'input.value', 'output.value', '/Users/']) {
    assert.ok(!all.includes(secret), `${secret} must not be exported`);
  }
});

test('opt-in: captureContent exports the prompt and the tool arguments and result, never a key', async () => {
  const { spans } = await runAgent(server, { captureContent: true });
  const [root] = byName(spans, 'invoke_agent');
  assert.ok(root.attributes['input.value'].includes(MARKER));
  const [tool] = byName(spans, 'execute_tool ');
  assert.ok(tool.attributes['input.value'].includes('Lisbon'));
  assert.ok(tool.attributes['output.value'].includes(MARKER));
  assert.ok(!everything(spans).includes('sk-or-FAKE-KEY-0001'));
});

test('a failing tool is an ERROR span; its text is exported only with content on, its stack never', async () => {
  const off = await runAgent(server, { toolFails: true });
  const [toolOff] = byName(off.spans, 'execute_tool ');
  assert.equal(toolOff.status.code, SpanStatusCode.ERROR);
  assert.equal(toolOff.attributes['error.type'], 'Error');
  assert.equal(toolOff.status.message, 'Error');
  assert.equal(toolOff.events.length, 0);
  for (const secret of [MARKER, '/Users/', 'secret/path', 'weather service down']) assert.ok(!everything(off.spans).includes(secret));

  const on = await runAgent(server, { toolFails: true, captureContent: true });
  const [toolOn] = byName(on.spans, 'execute_tool ');
  assert.ok(toolOn.attributes['error.message'].includes(MARKER));
  assert.ok(!everything(on.spans).includes('stack'));
  assert.ok(!everything(on.spans).includes('    at '));
});

test('a rejected model request ends the agent span as ERROR with the reason only', async () => {
  const { spans, error } = await runAgent(server, { model: 'no-such-model-for-this-demo' });
  assert.ok(error);
  const [root] = byName(spans, 'invoke_agent');
  assert.equal(root.status.code, SpanStatusCode.ERROR);
  assert.equal(root.status.message, 'error');
  assert.ok(!everything(spans).includes('no such model'));
});

test('the exporter posts uncompressed OTLP with both keys to /tracer/v1/traces', async () => {
  const seen = [];
  const collector = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    seen.push({ url: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
    res.writeHead(200, { 'content-type': 'application/json' }).end('{}');
  });
  await new Promise((r) => collector.listen(0, '127.0.0.1', r));
  const provider = buildTracerProvider({
    projectName: 'wire-check',
    baseUrl: `http://127.0.0.1:${collector.address().port}/`,
    apiKey: 'key-a',
    secretKey: 'key-b',
  });
  provider.getTracer('t').startSpan('x').end();
  await provider.shutdown();
  collector.close();
  assert.equal(seen.length, 1);
  assert.equal(seen[0].url, '/tracer/v1/traces');
  assert.equal(seen[0].headers['x-api-key'], 'key-a');
  assert.equal(seen[0].headers['x-secret-key'], 'key-b');
  assert.equal(seen[0].headers['content-encoding'], undefined);
  assert.ok(seen[0].body.includes('wire-check'));
});

test('buildTracerProvider refuses to start without both keys', () => {
  assert.throws(() => buildTracerProvider({ apiKey: 'a', secretKey: '' }), /FI_SECRET_KEY/);
});
