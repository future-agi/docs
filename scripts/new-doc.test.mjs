import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('F7 integration scaffolding points authors to the catalog with every required field', () => {
  // Same isolated fixture as the independent verifier's new-doc proof. Never
  // scaffold a test route into the checkout or silently choose product metadata.
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'docs-new-integration-'));
  try {
    fs.mkdirSync(path.join(fixture, 'src/lib'), { recursive: true });
    for (const file of ['navigation.ts', 'integrations.mjs']) {
      fs.copyFileSync(path.join(root, 'src/lib', file), path.join(fixture, 'src/lib', file));
    }
    const navBefore = fs.readFileSync(path.join(fixture, 'src/lib/navigation.ts'), 'utf8');
    const catalogBefore = fs.readFileSync(path.join(fixture, 'src/lib/integrations.mjs'), 'utf8');
    const result = spawnSync(process.execPath, [path.join(root, 'scripts/new-doc.mjs'), 'docs/integrations/traceai/acceptance-only-provider', 'Acceptance Provider'], { cwd: fixture, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.ok(fs.existsSync(path.join(fixture, 'src/pages/docs/integrations/traceai/acceptance-only-provider.mdx')));
    assert.match(result.stdout, /src\/lib\/integrations\.mjs/);
    assert.doesNotMatch(result.stdout, /Add this line to src\/lib\/navigation\.ts/);
    for (const field of ['id', 'name', 'href', 'category', 'summary', 'method', 'logo']) assert.match(result.stdout, new RegExp(`\\b${field}:`), field);
    assert.match(result.stdout, /test:integrations/);
    assert.match(result.stdout, /manifest\.json/);
    assert.equal(fs.readFileSync(path.join(fixture, 'src/lib/navigation.ts'), 'utf8'), navBefore);
    assert.equal(fs.readFileSync(path.join(fixture, 'src/lib/integrations.mjs'), 'utf8'), catalogBefore);
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});

test('ordinary documentation scaffolding still registers literal navigation siblings', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'docs-new-page-'));
  try {
    fs.mkdirSync(path.join(fixture, 'src/lib'), { recursive: true });
    fs.writeFileSync(path.join(fixture, 'src/lib/navigation.ts'), "export const items = [\n  { title: 'Existing', href: '/docs/evaluation/existing' },\n];\n");
    const result = spawnSync(process.execPath, [path.join(root, 'scripts/new-doc.mjs'), 'docs/evaluation/example', 'Example'], { cwd: fixture, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.match(fs.readFileSync(path.join(fixture, 'src/lib/navigation.ts'), 'utf8'), /href: '\/docs\/evaluation\/example'/);
  } finally { fs.rmSync(fixture, { recursive: true, force: true }); }
});
