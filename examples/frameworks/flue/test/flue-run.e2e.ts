// Real Flue (CLI, runtime, built server, standalone script) and this recipe's
// files, with no keys: run_e2e.sh against a deterministic OpenAI-compatible mock
// model and a loopback sink standing in for Future AGI. Run: npm run test:flue
// (about two minutes; builds the server and starts Flue several times).
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after, before, describe, test } from 'node:test';

import { startMockModel } from '../scripts/mock-model.mjs';
import { startRecorder } from '../scripts/recorder.mjs';

const EXAMPLE = fileURLToPath(new URL('..', import.meta.url));

function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => { const { port } = s.address() as { port: number }; s.close(() => resolve(port)); });
  });
}

describe('run_e2e.sh with a mock model', { timeout: 600_000 }, () => {
  let sink: Awaited<ReturnType<typeof startRecorder>>;
  let mock: Awaited<ReturnType<typeof startMockModel>>;
  before(async () => { sink = await startRecorder({ port: 0 }); mock = await startMockModel({ port: 0 }); });
  after(() => { sink.server.close(); mock.server.close(); });

  test('every phase runs and every wire check passes', async () => {
    const out = mkdtempSync(join(tmpdir(), 'flue-e2e-'));
    const proc = spawn('./run_e2e.sh', [], {
      cwd: EXAMPLE,
      env: {
        PATH: process.env.PATH ?? '',
        HOME: process.env.HOME ?? '',
        FI_API_KEY: 'hermetic-api-key',
        FI_SECRET_KEY: 'hermetic-secret-key',
        FI_BASE_URL: `http://127.0.0.1:${sink.port}`,
        FI_PROJECT_NAME: 'flue-hermetic',
        MODEL_BASE_URL: `http://127.0.0.1:${mock.port}/v1`,
        MODEL_API_KEY: 'mock-key',
        MODEL_ID: 'mock-model',
        RECORDER_PORT: String(await freePort()),
        SERVER_PORT: String(await freePort()),
        OUT: out,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let log = '';
    proc.stdout.on('data', (d) => (log += d));
    proc.stderr.on('data', (d) => (log += d));
    const code: number | null = await new Promise((resolve) => proc.on('exit', resolve));
    assert.equal(code, 0, log);
    assert.match(log, /all \d+ checks passed/);
    assert.doesNotMatch(log, /^FAIL /m);
    assert.ok(sink.requests.length > 0, 'the sink received the forwarded OTLP requests');
  });
});
