import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

test('the standalone script parses on the current supported Node runtime', () => {
  const script = fileURLToPath(new URL('../scripts/ask.ts', import.meta.url));
  const result = spawnSync(process.execPath, ['--check', script], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
});
