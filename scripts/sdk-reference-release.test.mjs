// @ts-check
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decide, newestPythonTag, newestRelease, newestTag, resolve } from './sdk-reference-release.mjs';

const SHA = 'd4631b0b5208e11ef55706b531609be427888704';
const files = {
  '.release-please-manifest.json': JSON.stringify({ python: '0.7.0', 'typescript/futureagi': '0.2.0' }),
  'sdkgen/contracts/BACKEND_VERSION': 'v1.58.0\n',
};

/** @param {{pypi?: boolean, npm?: boolean, tags?: string[], shas?: Record<string, string>, dates?: Record<string, string>, trees?: Record<string, string>}} world */
function io(world = {}) {
  return {
    resolveSha: async (/** @type {string} */ ref) => (ref === 'missing' ? Promise.reject(new Error('404')) : (world.shas?.[ref] ?? SHA)),
    fileAt: async (/** @type {string} */ path, /** @type {string} */ sha) => {
      if (path === '.release-please-manifest.json') {
        const tag = Object.entries(world.shas ?? {}).find(([tag, commit]) => tag.startsWith('typescript-') && commit === sha)?.[0];
        const pythonTag = Object.entries(world.shas ?? {}).find(([tag, commit]) => tag.startsWith('python-') && commit === sha)?.[0];
        return JSON.stringify({ python: pythonTag?.replace('python-v', '') ?? '0.7.0', 'typescript/futureagi': tag?.replace('typescript-v', '') ?? '0.2.0' });
      }
      return files[path];
    },
    commitDate: async (/** @type {string} */ sha) => world.dates?.[sha] ?? '2026-11-05T03:41:58Z',
    packageTree: async (/** @type {string} */ sha, /** @type {string} */ directory) => world.trees?.[`${sha}:${directory}`] ?? `${directory}-unchanged`,
    tags: async () => (world.tags ?? ['python-v0.6.9', 'python-v0.7.0', 'python-v0.6.14', 'typescript-v0.2.0']).map((t) => ({ ref: `refs/tags/${t}` })),
    onPyPI: async () => world.pypi ?? false,
    onNpm: async () => world.npm ?? false,
  };
}

test('newest python tag is chosen by version, not by string order', () => {
  const tags = ['python-v0.9.1', 'python-v0.10.0', 'python-v0.9.12'].map((t) => ({ ref: `refs/tags/${t}` }));
  assert.equal(newestPythonTag(tags), 'python-v0.10.0');
  assert.throws(() => newestPythonTag([{ ref: 'refs/tags/typescript-v0.2.0' }]), /no python-v\* release tag/);
});

test('the scheduled default follows both release streams: a newer TypeScript-only release wins', async () => {
  const A = 'a'.repeat(40); // python-v0.7.0 and typescript-v0.2.0 shipped here
  const B = 'b'.repeat(40); // typescript-v0.2.1 shipped later, from a newer SDK commit with newer pages
  const world = {
    tags: ['python-v0.7.0', 'typescript-v0.2.0', 'typescript-v0.2.1'],
    shas: { 'python-v0.7.0': A, 'typescript-v0.2.0': A, 'typescript-v0.2.1': B },
    dates: { [A]: '2026-11-05T03:41:58Z', [B]: '2026-11-09T10:00:00Z' },
  };
  const chosen = await newestRelease(io(world).tags && (await io(world).tags()), io(world).resolveSha, io(world).commitDate);
  assert.deepEqual(chosen, { ref: 'typescript-v0.2.1', sha: B }, 'the later commit, not the newest Python tag');
  const resolved = await resolve({}, io({ ...world, pypi: true, npm: true }));
  assert.equal(resolved.sha, B);
  assert.equal(resolved.ref, 'typescript-v0.2.1');
  assert.equal(resolved.publish, 'ready');
  assert.equal(resolved.releaseCommit, true);
  // The other way round too: a newer Python-only release is not shadowed by TypeScript.
  const flipped = { ...world, dates: { [A]: '2026-11-09T10:00:00Z', [B]: '2026-11-05T03:41:58Z' } };
  assert.equal((await resolve({}, io({ ...flipped, pypi: true, npm: true }))).sha, A);
  // One stream only is still a release; no stream at all fails closed.
  assert.equal(newestTag([{ ref: 'refs/tags/typescript-v0.2.0' }], 'python-'), null);
  assert.equal((await newestRelease([{ ref: 'refs/tags/typescript-v0.2.0' }], async () => B, async () => '2026-11-09T10:00:00Z')).sha, B);
  await assert.rejects(newestRelease([{ ref: 'refs/tags/v1' }], async () => A, async () => ''), /no python-v\* or typescript-v\* release tag/);
});

test('one branch per SDK version pair; preview branches are keyed by commit', () => {
  const facts = { sha: SHA, python: '0.7.0', typescript: '0.2.0' };
  assert.deepEqual(decide({ ...facts, stage: 'released', installable: true }), {
    branch: 'sdk-reference/python-v0.7.0-typescript-v0.2.0', publish: 'ready', stage: 'released',
  });
  assert.deepEqual(decide({ ...facts, stage: 'candidate', installable: false }), {
    branch: 'sdk-reference/python-v0.7.0-typescript-v0.2.0', publish: 'draft', stage: 'candidate',
  });
  assert.deepEqual(decide({ ...facts, stage: 'preview', installable: false }), {
    branch: 'sdk-reference/preview-d4631b0b5208', publish: 'draft', stage: 'preview',
  });
  assert.throws(() => decide({ ...facts, stage: 'stable', installable: true }), /stage must be one of/);
});

test('a released claim stays a draft until both packages are installable', async () => {
  const claim = { ref: SHA, stage: 'released' };
  assert.equal((await resolve(claim, io({ pypi: true, npm: true }))).publish, 'ready');
  const onlyPython = await resolve(claim, io({ pypi: true, npm: false }));
  assert.equal(onlyPython.publish, 'draft');
  assert.equal(onlyPython.stage, 'candidate');
  assert.equal((await resolve(claim, io({ pypi: false, npm: true }))).publish, 'draft');
});

test('published version strings on an unreleased commit do not authorize stable docs', async () => {
  const released = 'a'.repeat(40);
  const result = await resolve({ ref: 'dev', stage: 'released' }, io({
    pypi: true, npm: true,
    shas: { dev: SHA, 'python-v0.7.0': released, 'typescript-v0.2.0': released },
  }));
  assert.equal(result.installable, true);
  assert.equal(result.releaseCommit, false);
  assert.equal(result.publish, 'draft');
  assert.equal(result.stage, 'candidate');
});

test('independent releases require unchanged source for the package that did not release', async () => {
  const A = 'a'.repeat(40);
  const B = 'b'.repeat(40);
  const world = { pypi: true, npm: true, tags: ['python-v0.8.0', 'typescript-v0.2.0'], shas: { release: B, 'python-v0.8.0': B, 'typescript-v0.2.0': A } };
  assert.equal((await resolve({ ref: 'release', stage: 'released' }, io(world))).publish, 'ready');
  const changedTS = { ...world, trees: { [`${A}:typescript/futureagi`]: 'published', [`${B}:typescript/futureagi`]: 'unreleased' } };
  assert.equal((await resolve({ ref: 'release', stage: 'released' }, io(changedTS))).publish, 'draft');
  const changedPython = { pypi: true, npm: true, tags: ['python-v0.7.0', 'typescript-v0.2.0'], shas: { release: B, 'python-v0.7.0': A, 'typescript-v0.2.0': B }, trees: { [`${A}:python`]: 'published', [`${B}:python`]: 'unreleased' } };
  assert.equal((await resolve({ ref: 'release', stage: 'released' }, io(changedPython))).publish, 'draft');
  await assert.rejects(resolve({ ref: 'release', stage: 'released' }, { ...io(world), packageTree: async () => { throw new Error('tree lookup failed'); } }), /tree lookup failed/);
});

test('missing release tags cannot authorize stable docs and lookup errors fail closed', async () => {
  assert.equal((await resolve({ ref: SHA, stage: 'released' }, io({ pypi: true, npm: true, tags: [] }))).publish, 'draft');
  await assert.rejects(resolve({ ref: SHA, stage: 'released' }, {
    ...io({ pypi: true, npm: true }), tags: async () => { throw new Error('HTTP 502'); },
  }), /HTTP 502/);
});

test('no ref means the newest published release; a ref without a stage is a preview', async () => {
  const release = await resolve({}, io({ pypi: true, npm: true }));
  assert.equal(release.ref, 'python-v0.7.0');
  assert.equal(release.stage, 'released');
  assert.equal(release.publish, 'ready');
  assert.equal(release.backend, 'v1.58.0');
  const preview = await resolve({ ref: 'dev' }, io({ pypi: true, npm: true }));
  assert.equal(preview.stage, 'preview');
  assert.equal(preview.publish, 'draft');
  assert.equal(preview.installable, false, 'registries are not consulted for a preview');
});

test('candidate and released runs for the same versions share a branch', async () => {
  const candidate = await resolve({ ref: SHA, stage: 'candidate' }, io());
  const released = await resolve({ ref: SHA, stage: 'released' }, io({ pypi: true, npm: true }));
  assert.equal(candidate.branch, released.branch);
  assert.equal(candidate.publish, 'draft');
  assert.equal(released.publish, 'ready');
});

test('an unresolvable ref or a manifest without both versions fails', async () => {
  await assert.rejects(resolve({ ref: 'missing' }, io()), /404/);
  const broken = { ...io(), fileAt: async () => JSON.stringify({ python: '0.7.0' }) };
  await assert.rejects(resolve({ ref: SHA }, broken), /lacks the python or typescript/);
});
