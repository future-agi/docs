// The recipe's telemetry module, in a child process, against a loopback recorder.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { after, before, describe, test } from 'node:test';

import { startRecorder } from '../scripts/recorder.mjs';

const EXAMPLE = fileURLToPath(new URL('..', import.meta.url));
type Rec = Awaited<ReturnType<typeof startRecorder>>;

function emit(env: Record<string, string>): Promise<{ code: number | null; stderr: string }> {
  return new Promise((resolve) => {
    const proc = spawn(process.execPath, ['test/helpers/emit-span.ts'], {
      cwd: EXAMPLE,
      env: { PATH: process.env.PATH ?? '', ...env },
      stdio: ['ignore', 'ignore', 'pipe'],
    });
    let stderr = '';
    proc.stderr.on('data', (d) => (stderr += d));
    proc.on('exit', (code) => resolve({ code, stderr }));
  });
}

describe('telemetry.ts', () => {
  let rec: Rec;
  before(async () => { rec = await startRecorder({ port: 0 }); });
  after(() => rec.server.close());

  test('exports to $FI_BASE_URL/tracer/v1/traces, uncompressed protobuf, both headers, resource project_name', async () => {
    rec.requests.length = 0;
    const { code } = await emit({
      FI_BASE_URL: `http://127.0.0.1:${rec.port}`,
      FI_API_KEY: 'unit-api-key',
      FI_SECRET_KEY: 'unit-secret-key',
      FI_PROJECT_NAME: 'unit-project',
    });
    assert.equal(code, 0);
    assert.equal(rec.requests.length, 1, 'one batch, delivered by the flush');
    const [r] = rec.requests;
    assert.equal(r.url, '/tracer/v1/traces');
    assert.equal(r.method, 'POST');
    assert.equal(r.rawHeaders['x-api-key'], 'unit-api-key');
    assert.equal(r.rawHeaders['x-secret-key'], 'unit-secret-key');
    assert.equal(r.rawHeaders['content-type'], 'application/x-protobuf');
    assert.equal(r.rawHeaders['content-encoding'], undefined);
    assert.equal(r.spans.length, 1);
    assert.equal(r.spans[0].name, 'probe');
    // Only the three attributes the recipe sets: no host.name, process.owner, process.command_args, ...
    assert.deepEqual(r.spans[0].resource, { project_name: 'unit-project', project_type: 'observe', 'service.name': 'unit-project' });
  });

  test('one missing key turns tracing off with a warning, and nothing is sent', async () => {
    rec.requests.length = 0;
    const { code, stderr } = await emit({ FI_BASE_URL: `http://127.0.0.1:${rec.port}`, FI_API_KEY: 'only-one-key' });
    assert.equal(code, 0);
    assert.match(stderr, /FI_API_KEY and FI_SECRET_KEY must both be set/);
    assert.equal(rec.requests.length, 0);
  });
});
