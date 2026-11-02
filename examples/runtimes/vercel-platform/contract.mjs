import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const pagePath = path.resolve(here, '../../../src/pages/docs/integrations/runtimes/vercel.mdx');
const page = await fs.readFile(pagePath, 'utf8');
const snippet = title => {
  const match = page.match(new RegExp('```javascript title="' + title.replaceAll('.', '\\.') + '"\\n([\\s\\S]*?)```'));
  assert.ok(match, `Missing documented ${title}`);
  return match[1];
};
const attrs = entries => Object.fromEntries((entries ?? []).map(({ key, value }) => [key, value.stringValue ?? value.intValue ?? value.boolValue]));
const packets = [];
const collector = http.createServer(async (req, res) => {
  let body = '';
  for await (const chunk of req) body += chunk;
  try {
    packets.push({ url: req.url, headers: req.headers, payload: JSON.parse(body) });
    res.writeHead(200, { 'content-type': 'application/json' }).end('{}');
  } catch {
    res.writeHead(400).end();
  }
});
collector.listen(0, '127.0.0.1');
await once(collector, 'listening');
const endpoint = `http://127.0.0.1:${collector.address().port}/tracer/v1/traces`;
const app = await fs.mkdtemp(path.join(here, '.contract-'));
let child;
let output = '';
let exited = false;
const request = (port, route, headers = {}) => new Promise((resolve, reject) => {
  const req = http.get({ hostname: '127.0.0.1', port, path: route, headers }, res => {
    let body = '';
    res.on('data', chunk => body += chunk);
    res.on('end', () => resolve({ status: res.statusCode, body }));
  });
  req.on('error', reject);
  req.setTimeout(30000, () => req.destroy(new Error(`Request timeout:\n${output}`)));
});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  await fs.mkdir(path.join(app, 'pages/api'), { recursive: true });
  await fs.mkdir(path.join(app, 'home'));
  await fs.writeFile(path.join(app, 'package.json'), JSON.stringify({ private: true, type: 'module' }));
  await fs.writeFile(path.join(app, 'instrumentation.js'), snippet('instrumentation.js').replace('https://api.futureagi.com/tracer/v1/traces', endpoint));
  await fs.writeFile(path.join(app, 'pages/api/health.js'), snippet('pages/api/health.js'));
  await fs.writeFile(path.join(app, 'pages/api/failure.js'), 'export default function handler() { throw new Error("synthetic-route-failure"); }');
  for (const credentials of [{}, { FI_API_KEY: 'synthetic-fi-api' }, { FI_SECRET_KEY: 'synthetic-fi-secret' }]) {
    const missing = spawnSync(process.execPath, ['--input-type=module', '-e', 'import {register} from "./instrumentation.js"; await register();'], {
      cwd: app, env: { PATH: process.env.PATH, NEXT_RUNTIME: 'nodejs', ...credentials }, encoding: 'utf8', timeout: 10000,
    });
    assert.equal(missing.status, 1);
    assert.match(missing.stderr, /Set FI_API_KEY and FI_SECRET_KEY/);
  }
  const edge = spawnSync(process.execPath, ['--input-type=module', '-e', 'import {register} from "./instrumentation.js"; await register();'], {
    cwd: app, env: { PATH: process.env.PATH, NEXT_RUNTIME: 'edge' }, encoding: 'utf8', timeout: 10000,
  });
  assert.equal(edge.status, 0, edge.stderr);
  child = spawn(process.execPath, [path.join(here, 'node_modules/next/dist/bin/next'), 'dev', '--webpack', '--hostname', '127.0.0.1', '--port', '0'], {
    cwd: app,
    env: {
      PATH: process.env.PATH, HOME: path.join(app, 'home'), TMPDIR: app,
      NEXT_TELEMETRY_DISABLED: '1', FI_API_KEY: 'synthetic-fi-api', FI_SECRET_KEY: 'synthetic-fi-secret',
      OTEL_BSP_SCHEDULE_DELAY: '100', OTEL_TRACES_SAMPLER: 'always_on',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.on('data', chunk => output += chunk);
  child.stderr.on('data', chunk => output += chunk);
  child.on('exit', () => exited = true);
  child.on('error', err => { output += String(err); exited = true; });
  let port;
  for (let i = 0; i < 300; i++) {
    if (exited) throw new Error(`Next.js exited before ready:\n${output}`);
    const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
    if (match && /Ready in/.test(output)) { port = Number(match[1]); break; }
    await delay(100);
  }
  assert.ok(port, `Next.js did not become ready:\n${output}`);
  const response = await request(port, '/api/health');
  assert.equal(response.status, 200);
  assert.deepEqual(JSON.parse(response.body), { status: 'ok' });
  const hasRequest = () => packets.some(packet => packet.payload.resourceSpans?.some(resource => resource.scopeSpans?.some(scope => scope.spans?.some(span => span.name.includes('/api/health')))));
  for (let i = 0; i < 200 && !hasRequest(); i++) await delay(100);
  assert.ok(hasRequest(), `Native request spans were not exported:\n${output}`);
  const inboundTrace = '11111111111111111111111111111111';
  const inboundParent = '2222222222222222';
  const failure = await request(port, '/api/failure', { traceparent: `00-${inboundTrace}-${inboundParent}-01` });
  assert.equal(failure.status, 500);
  const hasFailure = () => packets.some(packet => packet.payload.resourceSpans?.some(resource => resource.scopeSpans?.some(scope => scope.spans?.some(span => span.name === 'GET /api/failure'))));
  for (let i = 0; i < 200 && !hasFailure(); i++) await delay(100);
  assert.ok(hasFailure(), 'Missing native failed-request span');
  const spans = [];
  for (const packet of packets) {
    assert.equal(packet.url, '/tracer/v1/traces');
    assert.equal(packet.headers['x-api-key'], 'synthetic-fi-api');
    assert.equal(packet.headers['x-secret-key'], 'synthetic-fi-secret');
    assert.match(packet.headers['content-type'], /application\/json/);
    for (const resource of packet.payload.resourceSpans) {
      const resourceAttrs = attrs(resource.resource.attributes);
      assert.equal(resourceAttrs.project_name, 'vercel-web');
      assert.equal(resourceAttrs.project_type, 'observe');
      assert.equal(resourceAttrs['service.name'], 'vercel-web');
      for (const scope of resource.scopeSpans) spans.push(...scope.spans);
    }
  }
  const requestSpans = spans.filter(span => span.name.includes('/api/health'));
  assert.ok(requestSpans.length > 0, 'Missing native Next.js request span');
  assert.equal(new Set(spans.map(span => span.spanId)).size, spans.length, 'Duplicate export');
  assert.equal(new Set(requestSpans.map(span => span.traceId)).size, 1, 'Request context split');
  assert.equal(requestSpans.filter(span => !span.parentSpanId).length, 1, 'Expected one native request root');
  for (const span of requestSpans) {
    assert.ok(BigInt(span.endTimeUnixNano) >= BigInt(span.startTimeUnixNano));
    assert.equal(attrs(span.attributes)['fi.span.kind'], undefined, 'Do not manufacture AI classifications');
    if (span.parentSpanId) assert.ok(spans.some(parent => parent.spanId === span.parentSpanId), 'Broken parent linkage');
  }
  const failedRoot = spans.find(span => span.name === 'GET /api/failure');
  assert.equal(failedRoot.traceId, inboundTrace, 'Inbound W3C trace context lost');
  assert.equal(failedRoot.parentSpanId, inboundParent, 'Inbound parent lost');
  assert.equal(failedRoot.status.code, 2, 'Failed request did not retain error status');
  assert.equal(Number(attrs(failedRoot.attributes)['http.status_code']), 500);
  const serialized = JSON.stringify(packets.map(packet => packet.payload));
  assert.ok(!serialized.includes('synthetic-fi-api') && !serialized.includes('synthetic-fi-secret'), 'Auth leaked into telemetry');
  if (process.env.OTLP_CAPTURE) await fs.writeFile(process.env.OTLP_CAPTURE, JSON.stringify(packets.map(packet => packet.payload), null, 2));
  console.log(JSON.stringify({ result: 'PASS', packets: packets.length, spans: spans.map(span => ({ name: span.name, spanId: span.spanId, parentSpanId: span.parentSpanId, attributes: attrs(span.attributes) })) }));
} finally {
  if (child && !exited) {
    const stopped = once(child, 'exit');
    child.kill('SIGTERM');
    const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
    await stopped;
    clearTimeout(timer);
  }
  collector.closeAllConnections();
  await new Promise(resolve => collector.close(resolve));
  await fs.rm(app, { recursive: true, force: true });
}
