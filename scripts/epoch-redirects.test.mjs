// Run: node --test scripts/epoch-redirects.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';

const sourcesByTarget = {
  '/docs/epoch': [
    '/docs/environments/concepts/epoch',
    '/docs/simulation/concepts/optimization',
  ],
  '/docs/epoch/run-an-epoch': [
    '/docs/environments/guides/run-epoch',
    '/docs/simulation/guides/fix-my-agent',
    '/docs/simulation/features/fix-my-agent',
    '/product/simulation/how-to/fix-my-agent',
    '/cookbook/cookbook18/chat-simulation-with-fix-my-agent',
    '/docs/simulation/guides/running-optimizations',
    '/docs/cookbook/chat-simulation-fix-agent',
  ],
  '/docs/epoch/review-an-epoch': [
    '/docs/environments/guides/review-an-epoch',
    '/docs/simulation/guides/optimization-runs',
  ],
};

// Same parse as scripts/check-deleted-pages.mjs.
const raw = readFileSync('src/lib/redirects.ts', 'utf-8');
const redirects = new Map(
  [...raw.matchAll(/["']([^"']+)["']:\s*["']([^"']+)["']/g)].map(([, from, to]) => [from, to]),
);

for (const [target, sources] of Object.entries(sourcesByTarget)) {
  test(`${target} is a page, not a redirect`, () => {
    assert.ok(['.mdx', '/index.mdx'].some(suffix => existsSync(`src/pages${target}${suffix}`)));
    assert.equal(redirects.has(target), false);
  });
  for (const source of sources) {
    test(`${source} redirects directly to ${target}`, () => assert.equal(redirects.get(source), target));
  }
}
