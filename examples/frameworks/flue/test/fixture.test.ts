// The recorded fixture: three real Flue 2.3.0 runs recorded by run_e2e.sh with
// content off (a tool call, a failing tool, a failing model call). Identifiers,
// the model id and the model endpoint were replaced; nothing else was changed.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, test } from 'node:test';

import { CONTENT_KEYS, RESOURCE_KEYS } from '../scripts/check_wire.mjs';
import { prepareReplay } from '../scripts/replay_fixture.mjs';

const fixture = JSON.parse(readFileSync(fileURLToPath(new URL('./fixtures/flue-2.3.0-turns.otlp.json', import.meta.url)), 'utf8'));

type KV = { key: string; value: Record<string, unknown> };
const attrs = (kvs: KV[]) => Object.fromEntries(kvs.map(({ key, value }) => [key, Object.values(value)[0]]));
const rs = fixture.resourceSpans[0];
const spans: any[] = rs.scopeSpans.flatMap((ss: any) => ss.spans).map((s: any) => ({ ...s, a: attrs(s.attributes) }));
const byRun = (sub: string) => spans.filter((s) => s.a['flue.submission.id'] === sub);
const runs = [...new Set(spans.map((s) => s.a['flue.submission.id']))] as string[];

describe('flue-2.3.0-turns.otlp.json', () => {
  test('resource: project_name plus the two other keys the recipe sets, nothing else', () => {
    assert.deepEqual(Object.keys(attrs(rs.resource.attributes)).sort(), [...RESOURCE_KEYS].sort());
    assert.equal(rs.scopeSpans.length, 1);
    assert.equal(rs.scopeSpans[0].scope.name, '@flue/opentelemetry');
  });

  test('three runs, one trace each, invoke_agent root with chat and execute_tool children', () => {
    assert.equal(runs.length, 3);
    for (const sub of runs) assert.equal(new Set(byRun(sub).map((s) => s.traceId)).size, 1);
    const ok = byRun(runs[0]);
    const root = ok.find((s) => s.name === 'invoke_agent Weather');
    assert.ok(root && !root.parentSpanId);
    assert.deepEqual(ok.filter((s) => s.parentSpanId === root.spanId).map((s) => s.name).sort(), ['chat example-model', 'chat example-model', 'execute_tool get_weather']);
  });

  test('chat spans carry model, provider and token usage; the root carries none', () => {
    const chats = spans.filter((s) => s.name.startsWith('chat ') && s.status.code !== 2);
    assert.ok(chats.length >= 4);
    for (const c of chats) {
      assert.equal(c.a['gen_ai.request.model'], 'example-model');
      assert.ok(Number(c.a['gen_ai.usage.input_tokens']) > 0 && Number(c.a['gen_ai.usage.output_tokens']) > 0);
    }
    assert.ok(spans.filter((s) => s.name.startsWith('invoke_agent ')).every((s) => !('gen_ai.usage.input_tokens' in s.a)));
  });

  test('failures: tool ERROR keeps only the type, failed model call is ERROR on chat and root', () => {
    const tool = byRun(runs[1]).find((s) => s.name === 'execute_tool get_weather');
    assert.equal(tool.status.code, 2);
    assert.equal(tool.a['error.type'], 'Error');
    assert.deepEqual(tool.events.map((e: any) => [e.name, Object.keys(attrs(e.attributes))]), [['exception', ['exception.type']]]);
    const failed = byRun(runs[2]);
    assert.ok(failed.every((s) => s.status.code === 2));
    assert.ok(failed.some((s) => s.name.startsWith('chat ') && s.a['error.type']));
  });

  test('content off: no content attribute, no message, no stack trace', () => {
    for (const s of spans) {
      for (const k of CONTENT_KEYS) assert.ok(!(k in s.a), `${s.name} has ${k}`);
      assert.equal(s.status.message ?? '', '');
      for (const e of s.events ?? []) {
        const ea = attrs(e.attributes);
        assert.ok(!('exception.message' in ea) && !('exception.stacktrace' in ea));
      }
    }
  });

  test('replay: fresh ids, shifted to now, project renamed, parent links kept', () => {
    const { request, traceIds } = prepareReplay(fixture, { projectName: 'my-replay', nowNs: 1_800_000_000_000_000_000n });
    const out = request.resourceSpans[0].scopeSpans[0].spans;
    assert.equal(traceIds.length, 3);
    assert.ok(out.every((s: any) => !spans.some((o) => o.traceId === s.traceId || o.spanId === s.spanId)));
    assert.equal(attrs(request.resourceSpans[0].resource.attributes).project_name, 'my-replay');
    assert.equal(Math.max(...out.map((s: any) => Number(BigInt(s.endTimeUnixNano) / 1_000_000_000n))), 1_800_000_000);
    const ids = new Set(out.map((s: any) => s.spanId));
    assert.ok(out.every((s: any) => !s.parentSpanId || ids.has(s.parentSpanId)));
  });
});
