// @ts-check
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decide, newestPythonTag, resolve } from './sdk-reference-release.mjs';

const SHA = 'd4631b0b5208e11ef55706b531609be427888704';
const files = {
  '.release-please-manifest.json': JSON.stringify({ python: '0.7.0', 'typescript/futureagi': '0.2.0' }),
  'sdkgen/contracts/BACKEND_VERSION': 'v1.58.0\n',
};

/** @param {{pypi?: boolean, npm?: boolean, tags?: string[]}} world */
function io(world = {}) {
  return {
    resolveSha: async (/** @type {string} */ ref) => (ref === 'missing' ? Promise.reject(new Error('404')) : SHA),
    fileAt: async (/** @type {string} */ path) => files[path],
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
