// @ts-check
// Lifecycle tests for scripts/sdk-reference-pr.sh: the real script runs against a fake `gh`
// (a PR-state adapter persisted in a JSON file) and a fake `git`, so the assertions are on the
// PR state GitHub would hold after each event, not on the resolver's decision string.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const SCRIPT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'sdk-reference-pr.sh');

/** The fake `gh`: every PR mutation the script may issue, on a JSON state file. */
const FAKE_GH = `#!/usr/bin/env node
const fs = require('node:fs');
const file = process.env.FAKE_PR_STATE;
const state = JSON.parse(fs.readFileSync(file, 'utf-8'));
const save = () => fs.writeFileSync(file, JSON.stringify(state, null, 1));
const args = process.argv.slice(2);
const log = (line) => fs.appendFileSync(process.env.FAKE_LOG, line + '\\n');
log('gh ' + args.join(' '));
const [cmd, sub] = args;
const flag = (name) => { const i = args.indexOf(name); return i === -1 ? undefined : args[i + 1]; };
const open = () => state.prs.filter((p) => p.state === 'open');
if (cmd === 'pr' && sub === 'list') {
  const head = flag('--head');
  const hits = open().filter((p) => p.head === head);
  const jq = flag('--jq');
  const first = hits[0];
  if (jq && jq.includes('select(. != null)')) { if (first) process.stdout.write(first.number + ' ' + first.isDraft + '\\n'); process.exit(0); }
  process.stdout.write(JSON.stringify(hits.map((p) => ({ number: p.number, isDraft: p.isDraft }))));
  process.exit(0);
}
if (cmd === 'pr' && sub === 'create') {
  const number = state.next++;
  state.prs.push({ number, head: flag('--head'), state: 'open', isDraft: args.includes('--draft'), title: flag('--title') });
  save(); process.stdout.write('https://github.com/future-agi/docs/pull/' + number + '\\n'); process.exit(0);
}
const pr = state.prs.find((p) => String(p.number) === args[2]);
if (cmd === 'pr' && sub === 'view') { process.stdout.write(String(pr.isDraft) + '\\n'); process.exit(0); }
if (cmd === 'pr' && sub === 'edit') { pr.title = flag('--title'); pr.edits = (pr.edits || 0) + 1; save(); process.exit(0); }
if (cmd === 'pr' && sub === 'ready') {
  if (process.env.FAKE_READY_FAILS === '1') { process.stderr.write('GraphQL: forbidden\\n'); process.exit(1); }
  pr.isDraft = false; save(); process.exit(0);
}
if (cmd === 'pr' && sub === 'close') { pr.state = 'closed'; save(); process.exit(0); }
process.stderr.write('fake gh: unexpected ' + args.join(' ') + '\\n'); process.exit(64);
`;

/** The fake `git`: `diff --quiet` answers from FAKE_DIFF, pushes are recorded, the rest is a no-op. */
const FAKE_GIT = `#!/usr/bin/env node
const fs = require('node:fs');
const args = process.argv.slice(2);
fs.appendFileSync(process.env.FAKE_LOG, 'git ' + args.join(' ') + '\\n');
if (args[0] === 'diff' && args.includes('--quiet')) process.exit(process.env.FAKE_DIFF === '0' ? 0 : 1);
process.exit(0);
`;

function harness() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sdk-ref-pr-'));
  const bin = path.join(dir, 'bin');
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'gh'), FAKE_GH, { mode: 0o755 });
  fs.writeFileSync(path.join(bin, 'git'), FAKE_GIT, { mode: 0o755 });
  const stateFile = path.join(dir, 'prs.json');
  const logFile = path.join(dir, 'calls.log');
  fs.writeFileSync(stateFile, JSON.stringify({ next: 100, prs: [] }));
  fs.writeFileSync(logFile, '');
  const base = { SHA: 'a'.repeat(40), REF: 'python-v0.7.0', PY: '0.7.0', TS: '0.2.0', BACKEND: 'v1.58.0', SOURCE: 'test' };
  /** @param {{STAGE: string, PUBLISH: string, BRANCH?: string, SHA?: string, diff?: boolean, readyFails?: boolean}} ev */
  const run = (ev) => {
    const env = {
      ...process.env, ...base, SHA: ev.SHA ?? base.SHA,
      BRANCH: ev.BRANCH ?? 'sdk-reference/python-v0.7.0-typescript-v0.2.0',
      STAGE: ev.STAGE, PUBLISH: ev.PUBLISH,
      PATH: `${bin}:${process.env.PATH}`, FAKE_PR_STATE: stateFile, FAKE_LOG: logFile,
      FAKE_DIFF: ev.diff === false ? '0' : '1', FAKE_READY_FAILS: ev.readyFails ? '1' : '0', GH_TOKEN: 'fake',
    };
    const result = spawnSync('bash', [SCRIPT], { env, encoding: 'utf-8' });
    return { status: result.status, out: result.stdout + result.stderr };
  };
  const prs = () => JSON.parse(fs.readFileSync(stateFile, 'utf-8')).prs;
  const calls = () => fs.readFileSync(logFile, 'utf-8').trim().split('\n').filter(Boolean);
  const resetLog = () => fs.writeFileSync(logFile, '');
  return { run, prs, calls, resetLog };
}

test('candidate opens a draft; released promotes the same PR and verifies it; repeats are idempotent', () => {
  const h = harness();
  let r = h.run({ STAGE: 'candidate', PUBLISH: 'draft' });
  assert.equal(r.status, 0, r.out);
  assert.deepEqual(h.prs().map((p) => [p.number, p.isDraft, p.state]), [[100, true, 'open']]);
  assert.match(r.out, /#100 \(candidate, draft\)/);

  r = h.run({ STAGE: 'released', PUBLISH: 'ready' });
  assert.equal(r.status, 0, r.out);
  assert.deepEqual(h.prs().map((p) => [p.number, p.isDraft, p.state]), [[100, false, 'open']], 'same PR, now ready');
  assert.match(r.out, /#100 \(released, ready\)/);
  assert.ok(h.calls().some((c) => c === 'gh pr ready 100'), 'the promotion was issued');

  h.resetLog();
  r = h.run({ STAGE: 'released', PUBLISH: 'ready' });
  assert.equal(r.status, 0, r.out);
  assert.equal(h.prs().length, 1, 'a repeated released event opens no second PR');
  assert.ok(!h.calls().some((c) => c.startsWith('gh pr create')), 'no create on repeat');
  assert.ok(!h.calls().some((c) => c === 'gh pr ready 100'), 'no redundant promotion of a ready PR');
});

test('a stale candidate after released is ignored: the ready PR keeps its state, branch and body', () => {
  const h = harness();
  assert.equal(h.run({ STAGE: 'candidate', PUBLISH: 'draft' }).status, 0);
  assert.equal(h.run({ STAGE: 'released', PUBLISH: 'ready' }).status, 0);
  h.resetLog();
  const r = h.run({ STAGE: 'candidate', PUBLISH: 'draft', SHA: 'b'.repeat(40) });
  assert.equal(r.status, 0, r.out);
  assert.deepEqual(h.prs().map((p) => [p.number, p.isDraft]), [[100, false]], 'still ready');
  assert.match(r.out, /stale candidate event ignored/);
  assert.match(r.out, /::notice::/);
  const calls = h.calls();
  assert.ok(!calls.some((c) => c.startsWith('git push')), 'the released branch was not rewritten');
  assert.ok(!calls.some((c) => c.startsWith('gh pr edit')), 'the released title/body were not rewritten');
  assert.ok(!calls.some((c) => c.startsWith('gh pr ready') || c.startsWith('gh pr create')));
});

test('a failed promotion fails the run instead of reporting ready', () => {
  const h = harness();
  assert.equal(h.run({ STAGE: 'candidate', PUBLISH: 'draft' }).status, 0);
  const r = h.run({ STAGE: 'released', PUBLISH: 'ready', readyFails: true });
  assert.notEqual(r.status, 0, 'must not exit 0');
  assert.match(r.out, /could not mark future-agi\/docs#100 ready/);
  assert.deepEqual(h.prs().map((p) => p.isDraft), [true], 'the PR is honestly still a draft');
});

test('no diff against main: nothing is opened, and an open PR for the release is closed', () => {
  const h = harness();
  let r = h.run({ STAGE: 'released', PUBLISH: 'ready', diff: false });
  assert.equal(r.status, 0, r.out);
  assert.equal(h.prs().length, 0);
  assert.match(r.out, /nothing to open/);
  assert.equal(h.run({ STAGE: 'candidate', PUBLISH: 'draft' }).status, 0);
  r = h.run({ STAGE: 'released', PUBLISH: 'ready', diff: false });
  assert.equal(r.status, 0, r.out);
  assert.deepEqual(h.prs().map((p) => p.state), ['closed']);
});

test('a preview is its own draft PR on its own branch and never touches a release PR', () => {
  const h = harness();
  assert.equal(h.run({ STAGE: 'released', PUBLISH: 'ready' }).status, 0);
  const r = h.run({ STAGE: 'preview', PUBLISH: 'draft', BRANCH: 'sdk-reference/preview-bbbbbbbbbbbb', SHA: 'b'.repeat(40) });
  assert.equal(r.status, 0, r.out);
  assert.deepEqual(h.prs().map((p) => [p.head, p.isDraft]), [
    ['sdk-reference/python-v0.7.0-typescript-v0.2.0', false],
    ['sdk-reference/preview-bbbbbbbbbbbb', true],
  ]);
  assert.match(r.out, /#101 \(preview, draft\)/);
});

test('a missing decision variable is a usage error, not a half-run', () => {
  const h = harness();
  const r = h.run({ STAGE: 'released', PUBLISH: '' });
  assert.equal(r.status, 2);
  assert.match(r.out, /PUBLISH is not set/);
  assert.equal(h.prs().length, 0);
});
