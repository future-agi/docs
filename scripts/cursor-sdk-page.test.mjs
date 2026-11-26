import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/coding-agents/cursor-sdk.mdx', import.meta.url), 'utf8');

test('Cursor SDK has a distinct local-runtime catalog entry and released install pins', () => {
  const entry = integrations.find(({ id }) => id === 'cursor-sdk');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/cursor-sdk');
  assert.equal(entry?.category, 'coding');
  assert.equal(entry?.method, 'traceAI SDK');
  assert.notEqual(entry?.href, integrations.find(({ id }) => id === 'cursor')?.href);
  const install = '@traceai/cursor-sdk@0.1.1 @traceai/fi-core@1.1.1 @cursor/sdk@1.0.38';
  assert.ok(page.includes(`npm install ${install}`));
  assert.ok(page.includes(`pnpm add ${install}`));
  assert.match(page, /Node\.js 22\.13 or newer/);
  assert.match(page, /Cloud \(`bc-`\) agents are outside this guide's supported scope/);
});

test('Cursor SDK example is complete JavaScript with isolated tracing and guaranteed flush', () => {
  const example = page.match(/```javascript\n([\s\S]*?)\n```/)?.[1];
  assert.ok(example, 'Keep the runnable .mjs example');
  const parsed = spawnSync(process.execPath, ['--check', '--input-type=module'], {
    input: example,
    encoding: 'utf8',
  });
  assert.equal(parsed.status, 0, parsed.stderr);
  for (const text of [
    'import * as CursorSDK from "@cursor/sdk"',
    'import { register, ProjectType } from "@traceai/fi-core"',
    'import { CursorSDKInstrumentation, shutdown } from "@traceai/cursor-sdk"',
    'projectType: ProjectType.OBSERVE',
    'setGlobalTracerProvider: false',
    'new CursorSDKInstrumentation({ tracerProvider })',
    'instrumentation.manuallyInstrument(CursorSDK)',
    'local: { cwd: process.cwd() }',
    'for await (const event of run.stream())',
    'await run.wait()',
    'if (result.status !== "finished")',
    'if (followUp.status !== "finished")',
  ]) assert.ok(example.includes(text), text);
  assert.ok(example.indexOf('manuallyInstrument(CursorSDK)') < example.indexOf('Agent.create('));
  assert.match(example, /finally\s*\{\s*try\s*\{\s*await agent\?\.\[Symbol\.asyncDispose\]\(\);\s*\}\s*finally\s*\{\s*await shutdown\(tracerProvider\)/);
  assert.match(page, /node cursor-agent\.mjs/);
  assert.match(page, /same run produces both a \*\*Cursor Agent run\*\* trace and a \*\*Cursor session\*\* trace/);
  assert.match(page, /internal spans go to that provider/);
});

test('Cursor SDK documents callback capture and bounded task snapshots, not stream-only tracing', () => {
  assert.match(page, /per-send `onStep` and `onDelta` callbacks/);
  assert.match(page, /`wait\(\)`-only run or `Agent\.prompt\(\)` can therefore include child spans/);
  assert.match(page, /never consumes the single-reader stream itself/);
  assert.match(page, /identified tool calls are deduplicated across callbacks and the stream/);
  assert.match(page, /value\.conversationSteps/);
  assert.match(page, /not independently measured child execution/);
  assert.match(page, /Tasks without those snapshots remain a single tool span/);
  assert.doesNotMatch(page, /this version does not use them|from `run\.stream\(\)` only|Your code did not read `run\.stream\(\)`/);
});

test('Cursor SDK keeps raw errors behind content and independent error-detail gates', () => {
  const privacy = page.split('## Content and privacy\n')[1]?.split('\n## Limits')[0];
  assert.ok(privacy);
  assert.match(privacy, /removes error status messages and `cursor\.error\.message`, including fixed summaries/);
  assert.match(privacy, /hideInputs: false,\s*hideOutputs: false,\s*hideErrorDetails: true/);
  assert.match(privacy, /FI_HIDE_INPUTS=false/);
  assert.match(privacy, /FI_HIDE_OUTPUTS=false/);
  assert.match(privacy, /FI_HIDE_ERROR_DETAILS=true/);
  assert.match(privacy, /require \*\*all three\*\* resolved settings to be false: `hideInputs`, `hideOutputs` and `hideErrorDetails`/);
  assert.match(privacy, /Setting `hideErrorDetails: false` alone does not reveal raw errors/);
  assert.match(privacy, /Explicit code options take precedence over environment variables/);
  assert.match(page, /error status messages are omitted by default/);
  assert.doesNotMatch(page, /status message `RunError|status message such as `AuthenticationError/);
});

test('Cursor SDK guide has no public verification diary or account-testing narrative', () => {
  assert.doesNotMatch(page, /live verification|live vendor|Tested with|traced live|test account|live test|read 2026|fi_verify\.py|has not been run|not run end to end/i);
});
