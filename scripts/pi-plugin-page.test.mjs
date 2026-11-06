import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/pi.mdx', import.meta.url), 'utf8');
test('Pi has three setup steps and a maintained native extension, not customer-maintained glue', () => {
  assert.equal((page.match(/<Step title=/g) ?? []).length, 3);
  assert.match(page, /npx @traceai\/agents setup pi --project coding-agents/);
  assert.match(page, /pi install npm:@traceai\/pi-plugin/);
  assert.doesNotMatch(page, /curl -|git clone|run_e2e|install\.sh|provisional copy|FI_CAPTURE_CONTENT/);
  assert.match(page, /Pi\]\(https:\/\/pi.dev\) 1\.5\.0/);
});
test('Pi documents content-on privacy, status, kill switch and source-specific limitations', () => {
  for (const value of ['captured by default', '--no-capture-content', 'FI_AGENT_CAPTURE_CONTENT=false', 'FI_HIDE_ERROR_DETAILS', 'PI_CODING_AGENT_DIR', 'status pi --check', 'disable pi', 'one trace', 'estimates', 'subagent'])
    assert.ok(page.toLowerCase().includes(value.toLowerCase()), value);
  assert.match(page, /HTTP acceptance does not prove/);
  assert.match(page, /Manual compaction between prompts/);
  assert.doesNotMatch(page, /verified live|test runs|E2B|mock server|PASS\/FAIL/);
});
test('every local media reference exists', () => {
  for (const [,src] of page.matchAll(/(?:src=["']|!\[[^\]]*\]\()([^"')]+\.(?:png|webp|gif|mp4|webm))/g)) {
    if (src.startsWith('/')) assert.ok(existsSync(new URL(`../public${src}`, import.meta.url)), src);
  }
});
