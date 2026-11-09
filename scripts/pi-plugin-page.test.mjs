import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const pi = read('../src/pages/docs/integrations/coding-agents/pi.mdx');
const omp = read('../src/pages/docs/integrations/coding-agents/oh-my-pi.mdx');
const registry = read('../src/lib/integrations.mjs');

for (const [agent, page, nativeInstall] of [
  ['pi', pi, 'pi install npm:@traceai/pi-plugin'],
  ['oh-my-pi', omp, 'omp install npm:@traceai/oh-my-pi-plugin'],
]) {
  test(`${agent} has three setup steps with a maintained native plugin`, () => {
    assert.equal((page.match(/<Step title=/g) ?? []).length, 3);
    assert.ok(page.includes(`npx @traceai/agents setup ${agent} --project coding-agents`));
    assert.ok(page.includes(nativeInstall));
    assert.ok(page.includes('https://app.futureagi.com/dashboard/keys'));
    assert.doesNotMatch(page, /curl -|git clone|run_e2e|install\.sh|provisional copy|FI_CAPTURE_CONTENT/);
    assert.match(page, /working model configuration/);
  });
  test(`${agent} documents privacy, scopes and lifecycle controls`, () => {
    for (const value of ['captured by default', '--no-capture-content', 'FI_AGENT_CAPTURE_CONTENT=false',
      'FI_AGENT_ENABLED=false', 'PI_CODING_AGENT_DIR', 'credentials.json', 'futureagi.json',
      '--scope project', '--project-dir', '--user-only', '--replace-credentials', 'PROJECT_CONFIG_IGNORED',
      'agent-wide switch', 'not project-scoped',
      `status ${agent} --check`, `doctor ${agent}`, `disable ${agent}`, `enable ${agent}`, `uninstall ${agent}`,
      'one trace per prompt', 'estimates', 'subagent', 'HTTP acceptance does not prove']) {
      assert.ok(page.toLowerCase().includes(value.toLowerCase()), value);
    }
    assert.doesNotMatch(page, /verified live|test runs|E2B|mock server|PASS\/FAIL|internal hold|run ids/i);
  });
  test(`${agent} stays registered as a native-plugin route`, () => {
    const row = registry.split('\n').find((line) => line.includes(`id: '${agent}'`));
    assert.ok(row);
    assert.ok(row.includes(`href: '/docs/integrations/coding-agents/${agent}'`));
    assert.ok(row.includes("method: 'Native plugin'"));
  });
  test(`${agent} has no nonexistent local media references`, () => {
    for (const [, src] of page.matchAll(/(?:src=["']|!\[[^\]]*\]\()([^"')]+\.(?:png|webp|gif|mp4|webm))/g)) {
      if (src.startsWith('/')) assert.ok(existsSync(new URL(`../public${src}`, import.meta.url)), src);
    }
  });
}

test('Pi documents its supported host line, project install and child-boundary limitations', () => {
  for (const value of ['1.5.0 or later in the 1.x line', "Pi's local package installation", '.pi/futureagi.json',
    'uninstall pi --scope project', 'Run status from the project directory', 'hidden prompts',
    'Invalid replacements leave your saved profile unchanged', 'including when the conversation is resumed',
    'including environment credentials', 'FI_HIDE_ERROR_DETAILS', 'Manual compaction between prompts',
    'must explicitly report its own child boundaries']) {
    assert.ok(pi.includes(value), value);
  }
});

test('Oh My Pi documents prompt roots, generation coverage and user-scoped native installation', () => {
  for (const value of ['18.17.0 or later in the 18.x line', 'Bun 1.4.4 or later', 'reconstructed generations',
    'not full provider requests', 'Advisor and other auxiliary generations are not yet available',
    'spawning tool', 'linked continuation', '.omp/futureagi.json', 'always user-scoped',
    'omp plugin uninstall @traceai/oh-my-pi-plugin', 'OTEL_TRACES_EXPORTER=none',
    'not its logs or metrics', 'not a data-loss-prevention guarantee']) {
    assert.ok(omp.includes(value), value);
  }
  assert.doesNotMatch(omp, /one trace per session|one trace, with every model|off by default|\.omp\/hooks\/post\/|omp\.session/);
});
