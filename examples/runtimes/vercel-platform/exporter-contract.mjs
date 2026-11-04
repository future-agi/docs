import assert from 'node:assert/strict';
import { once } from 'node:events';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { BasicTracerProvider } from '@opentelemetry/sdk-trace-base';

const here = path.dirname(fileURLToPath(import.meta.url));
const page = await fs.readFile(path.resolve(here, '../../../src/pages/docs/integrations/runtimes/vercel.mdx'), 'utf8');
const snippet = page.match(/```javascript title="instrumentation.js"\n([\s\S]*?)```/)[1];
// Exercise the exporter's exact documented configuration without registering a second provider.
assert.equal(snippet.split('registerOTel({').length, 2);
const directory = await fs.mkdtemp(path.join(here, '.contract-exporter-'));
const spans = [];
const provider = new BasicTracerProvider({ spanProcessors: [{
  onStart() {}, onEnd(span) { spans.push(span); }, async forceFlush() {}, async shutdown() {},
}] });
provider.getTracer('exporter-contract').startSpan('synthetic-upload').end();
Object.assign(process.env, { NEXT_RUNTIME: 'nodejs', FI_API_KEY: 'synthetic-fi-api', FI_SECRET_KEY: 'synthetic-fi-secret' });
const failures = [];
try {
  for (const scenario of [
    { name: 'unauthorized', status: 401, recover: false, retry: false },
    { name: 'rate-limit-recovery', status: 429, recover: true, retry: true },
    { name: 'unavailable-recovery', status: 503, recover: true, retry: true },
    { name: 'persistent-rate-limit', status: 429, recover: false, retry: true },
    { name: 'persistent-unavailable', status: 503, recover: false, retry: true },
  ]) {
    const attempts = [];
    let accepted = 0;
    const server = http.createServer(async (req, res) => {
      let body = '';
      for await (const chunk of req) body += chunk;
      attempts.push({ body, headers: req.headers, url: req.url });
      const status = scenario.recover && attempts.length > 1 ? 200 : scenario.status;
      if (status === 200) accepted++;
      res.writeHead(status, { 'content-type': 'application/json', 'retry-after': '0' }).end('{}');
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    let exporter;
    try {
      const file = path.join(directory, `${scenario.name}.mjs`);
      await fs.writeFile(file, snippet.replace('registerOTel({', 'return ({').replace(
        'https://api.futureagi.com/tracer/v1/traces', `http://127.0.0.1:${server.address().port}/tracer/v1/traces`,
      ));
      const { register } = await import(pathToFileURL(file));
      ({ traceExporter: exporter } = await register());
      const result = await new Promise(resolve => exporter.export(spans, resolve));
      await exporter.forceFlush();
      console.log(JSON.stringify({ scenario: scenario.name, code: result.code, attempts: attempts.length, accepted }));
      assert.equal(result.code, scenario.recover ? 0 : 1, `${scenario.name}: rejected uploads must not report success`);
      assert.equal(accepted, scenario.recover ? 1 : 0, `${scenario.name}: retry must deliver exactly one batch`);
      if (scenario.recover) assert.equal(attempts.length, 2);
      else if (scenario.retry) assert.ok(attempts.length > 1 && attempts.length <= 6, 'Retries must be bounded');
      else assert.equal(attempts.length, 1, 'Do not retry invalid credentials');
      for (const attempt of attempts) {
        assert.equal(attempt.url, '/tracer/v1/traces');
        assert.equal(attempt.headers['x-api-key'], 'synthetic-fi-api');
        assert.equal(attempt.headers['x-secret-key'], 'synthetic-fi-secret');
        assert.match(attempt.headers['content-type'], /application\/json/);
        assert.equal(attempt.body, attempts[0].body, 'Retry must preserve the original batch');
        const payload = JSON.parse(attempt.body);
        assert.equal(payload.resourceSpans[0].scopeSpans[0].spans[0].name, 'synthetic-upload');
        assert.ok(!attempt.body.includes('synthetic-fi-api') && !attempt.body.includes('synthetic-fi-secret'));
      }
    } catch (error) {
      failures.push(error);
    } finally {
      await exporter?.shutdown();
      server.closeAllConnections();
      await new Promise(resolve => server.close(resolve));
    }
  }
  assert.deepEqual(failures.map(error => error.message), [], 'Collector rejection/recovery contract');
} finally {
  await provider.shutdown();
  await fs.rm(directory, { recursive: true, force: true });
}
