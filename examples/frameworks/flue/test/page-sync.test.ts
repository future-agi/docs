// The docs page must show exactly the files in this example and the versions
// this example installs.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, test } from 'node:test';

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
const page = read('../../../../src/pages/docs/integrations/frameworks/flue.mdx');
const pkg = JSON.parse(read('../package.json'));

/** Fenced blocks of the form ```lang title="path" ... ``` */
function titledBlocks(mdx: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of mdx.matchAll(/```\w+ title="([^"]+)"\n([\s\S]*?)```/g)) out.set(m[1], m[2]);
  return out;
}

describe('flue.mdx', () => {
  const blocks = titledBlocks(page);

  test('shows src/futureagi.ts, src/telemetry.ts and src/app.ts exactly as they are in the example', () => {
    for (const file of ['src/futureagi.ts', 'src/telemetry.ts', 'src/app.ts']) {
      assert.ok(blocks.has(file), `page has a block titled ${file}`);
      assert.equal(blocks.get(file), read(`../${file}`), `${file} differs from the page`);
    }
  });

  test('names the Flue and OpenTelemetry versions the example installs', () => {
    const d = pkg.dependencies;
    for (const name of ['@flue/runtime', '@flue/opentelemetry', '@flue/cli', '@flue/vite']) assert.equal(d[name], '2.3.0');
    assert.match(page, /Flue 2\.3\.0/);
    for (const name of ['@opentelemetry/sdk-node', '@opentelemetry/exporter-trace-otlp-proto']) assert.match(page, new RegExp(`\`${name}\` ${d[name].replaceAll('.', '\\.')}`));
    assert.match(page, new RegExp(`\`@opentelemetry/sdk-trace-base\` ${d['@opentelemetry/sdk-trace-base'].replaceAll('.', '\\.')}`));
  });

  test('uses the current API names and none of the removed ones outside the "Older guides" section', () => {
    const [current] = page.split('## Older guides');
    assert.match(current, /createOpenTelemetryInstrumentation/);
    assert.match(current, /instrument\(/);
    assert.doesNotMatch(current, /createOpenTelemetryObserv|exportContent|recording\.content/);
  });

  test('keeps the content and resource privacy setup without a verification diary', () => {
    assert.match(page, /content: false/);
    assert.match(page, /exception_stacktrace/);
    assert.match(page, /autoDetectResources: false/);
    assert.match(page, /Use opaque ids/);
    assert.doesNotMatch(page, /How this was checked:|In our run/);
  });

  test('install line lists every OpenTelemetry package the example imports', () => {
    const imports = [...read('../src/telemetry.ts').matchAll(/from '(@opentelemetry\/[^']+)'/g)].map((m) => m[1]);
    const install = /```bash\nnpm install ([^\n]+)\n```/.exec(page)?.[1] ?? '';
    const packages = install.split(/\s+/);
    for (const name of [...imports, '@flue/runtime', '@flue/opentelemetry']) {
      assert.ok(packages.includes(`${name}@${pkg.dependencies[name]}`), `${name} pinned to the example version`);
    }
  });
});
