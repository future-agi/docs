import http from 'node:http';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';

const received = [];
const server = http.createServer((req, res) => {
  const chunks = [];
  req.on('data', chunk => chunks.push(chunk));
  req.on('end', () => {
    received.push({ path: req.url, headers: req.headers, data: JSON.parse(Buffer.concat(chunks).toString()) });
    res.writeHead(200); res.end('{}');
  });
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
try {
  const child = spawn('./node_modules/.bin/vitest', ['run', '--maxWorkers=1'], {
    cwd: import.meta.dirname,
    env: { ...process.env,
      FI_API_KEY: 'synthetic-api-key', FI_SECRET_KEY: 'synthetic-secret-key',
      FI_PROJECT_NAME: 'vitest-synthetic', FI_OTLP_ENDPOINT: `http://127.0.0.1:${server.address().port}/v1/traces`,
    },
  });
  let stdout = '', stderr = '';
  child.stdout.on('data', data => stdout += data);
  child.stderr.on('data', data => stderr += data);
  const exit = await new Promise(resolve => child.on('close', resolve));
  assert.equal(exit, 0, `Vitest failed:\n${stdout}\n${stderr}`);
  const records = received.flatMap(batch => (batch.data.resourceSpans ?? []).flatMap(rs => {
    const resource = Object.fromEntries((rs.resource?.attributes ?? []).map(({key, value}) => [key, value.stringValue]));
    return (rs.scopeSpans ?? []).flatMap(group => (group.spans ?? []).map(span => ({ resource, span })));
  }));
  assert.ok(received.length > 0, 'No OTLP export');
  assert.ok(received.every(batch => batch.path === '/v1/traces' && batch.headers['x-api-key'] === 'synthetic-api-key' && batch.headers['x-secret-key'] === 'synthetic-secret-key'));
  assert.ok(records.every(({resource}) => resource.project_name === 'vitest-synthetic' && resource.project_type === 'observe'));
  const names = new Set(records.map(({span}) => span.name));
  assert.ok([...names].some(name => name.includes('vitest.worker')), `No worker span: ${[...names]}`);
  assert.ok([...names].some(name => name.includes('vitest.test')), `No test span: ${[...names]}`);
  const ids = new Set(records.map(({span}) => span.spanId));
  assert.ok(records.some(({span}) => span.parentSpanId && ids.has(span.parentSpanId)), 'No preserved parent linkage');
  console.log(`PASS: ${records.length} OTLP spans, worker/test, parent links, resource and auth headers`);
} finally { await new Promise(resolve => server.close(resolve)); }
