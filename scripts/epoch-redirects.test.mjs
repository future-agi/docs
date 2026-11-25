// The three retired Fix My Agent URLs must each reach Run Epoch in one hop.
// Run: node --test scripts/epoch-redirects.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';

const TARGET = '/docs/environments/guides/run-epoch';
const RETIRED = [
  '/docs/simulation/guides/fix-my-agent',
  '/docs/simulation/features/fix-my-agent',
  '/product/simulation/how-to/fix-my-agent',
];

// Same parse as scripts/check-deleted-pages.mjs.
const raw = readFileSync('src/lib/redirects.ts', 'utf-8');
const redirects = new Map(
  [...raw.matchAll(/["']([^"']+)["']:\s*["']([^"']+)["']/g)].map(([, from, to]) => [from, to]),
);

for (const from of RETIRED) {
  test(`${from} redirects straight to Run Epoch`, () => {
    assert.equal(redirects.get(from), TARGET);
    assert.equal(redirects.has(TARGET), false, 'the target must not redirect again');
  });
}

test('the Run Epoch page exists', () => {
  assert.ok(existsSync(`src/pages${TARGET}.mdx`));
});
