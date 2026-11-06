// The wire checker must fail when the recipe leaks. Builds a synthetic good run,
// then breaks it one way at a time.
import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { checkRun } from '../scripts/check_wire.mjs';

type Span = Record<string, any>;
const resource = (project = 'p') => ({ project_name: project, project_type: 'observe', 'service.name': project });
const scope = { name: '@flue/opentelemetry', version: '' };
let n = 0;
const span = (name: string, sub: string, parent: string, attributes: Span = {}, extra: Span = {}): Span => ({
  resource: resource(extra.project), scope, traceId: `t-${sub}`, spanId: `s${++n}`, parentSpanId: parent, name, kind: 1,
  attributes: { 'flue.submission.id': sub, ...attributes }, events: extra.events ?? [], status: extra.status ?? { code: 0, message: '' },
});
const chatAttrs = { 'gen_ai.request.model': 'm', 'gen_ai.provider.name': 'proxy', 'gen_ai.usage.input_tokens': 5, 'gen_ai.usage.output_tokens': 2 };

function tree(sub: string, extra: Span = {}): Span[] {
  const root = span('invoke_agent Weather', sub, '', {}, extra);
  return [
    root,
    span('chat m', sub, root.spanId, chatAttrs, extra),
    span('execute_tool get_weather', sub, root.spanId, { 'gen_ai.tool.name': 'get_weather', 'gen_ai.tool.call.id': 'c1' }, extra),
    span('chat m', sub, root.spanId, chatAttrs, extra),
  ];
}

function goodRun(mutate: (spans: Span[]) => void = () => {}) {
  const off = tree('sub-off');
  const toolerr = tree('sub-toolerr');
  toolerr[2].status = { code: 2, message: '' };
  toolerr[2].attributes['error.type'] = 'Error';
  toolerr[2].events = [{ name: 'exception', attributes: { 'exception.type': 'Error' } }];
  const model = [span('invoke_agent Weather', 'sub-model', '', {}, { status: { code: 2, message: '' } }), span('chat m', 'sub-model', 'x', { 'error.type': '_OTHER' }, { status: { code: 2, message: '' } })];
  const on = tree('sub-on', { project: 'p-optin' });
  on[1].attributes['gen_ai.input.messages'] = '[ONMARK]';
  on[1].attributes['gen_ai.system_instructions'] = '[]';
  on[1].attributes['gen_ai.tool.definitions'] = '[]';
  on[2].attributes['gen_ai.tool.call.arguments'] = '{"city":"ONMARK"}';
  on[2].attributes['gen_ai.tool.call.result'] = '{"city":"ONMARK"}';
  on[3].attributes['gen_ai.output.messages'] = '[ONMARK]';
  const onerr = tree('sub-onerr', { project: 'p-optin' });
  onerr[2].status = { code: 2, message: 'no station ONMARK' };
  onerr[2].events = [{ name: 'exception', attributes: { 'exception.type': 'Error', 'exception.message': 'no station ONMARK' } }];
  const server = tree('sub-server');
  const script = tree('sub-script');
  const all = [...off, ...toolerr, ...model, ...on, ...onerr, ...server, ...script];
  mutate(all);
  const requests = [{
    file: 'req-001.json',
    meta: { decodeError: null, headers: { 'x-api-key': '<set:3 chars>', 'x-secret-key': '<set:3 chars>' }, forwardStatus: 200, spans: all },
    raw: Buffer.from('nothing sensitive here'),
  }];
  const envs: Record<string, Span> = {
    'off.ok': { submissionId: 'sub-off', outcome: 'completed' }, 'off.toolerr': { submissionId: 'sub-toolerr', outcome: 'completed' },
    'model.err': { submissionId: 'sub-model', outcome: 'failed' }, 'on.ok': { submissionId: 'sub-on', outcome: 'completed' },
    'on.toolerr': { submissionId: 'sub-onerr', outcome: 'completed' }, 'server.ok': { submissionId: 'sub-server' },
    'script.ok': { submissionId: 'sub-script' }, 'down.ok': { outcome: 'completed', message: 'Cairo DWNMARK is sunny' },
  };
  return {
    requests,
    markers: { project: 'p', optinProject: 'p-optin', off: 'OFFMARK', err: 'ERRMARK', on: 'ONMARK', server: 'SRVMARK', script: 'SCRMARK', down: 'DWNMARK' },
    identity: { hostname: 'my-laptop.local', user: 'alice', home: '/Users/alice', cwd: '/Users/alice/app' },
    envelope: (name: string) => envs[name] ?? null,
    down: { exit: 0, elapsedMs: 10 },
  };
}

const failing = (run: ReturnType<typeof goodRun>) => checkRun(run, {}).filter((r) => !r.ok).map((r) => r.name);

describe('check_wire', () => {
  test('a clean run passes every check', () => {
    assert.deepEqual(failing(goodRun()), []);
  });

  test('a content attribute on a content-off span fails', () => {
    const run = goodRun((s) => { s[1].attributes['gen_ai.input.messages'] = 'x'; });
    assert.deepEqual(failing(run), ['off: no content attribute on any span']);
  });

  test('a host.name resource attribute fails', () => {
    const run = goodRun((s) => { s[0].resource['host.name'] = 'my-laptop.local'; });
    assert.deepEqual(failing(run), ['resource carries only project_name, project_type, service.name']);
  });

  test('a user name or local path on the wire fails', () => {
    const run = goodRun();
    run.requests[0].raw = Buffer.from('xx /Users/alice/app/src/tool.ts yy');
    assert.deepEqual(failing(run), ['no host name, user name or local path in any request, either mode']);
  });

  test('a marker on the wire in a content-off phase fails', () => {
    const run = goodRun();
    run.requests[0].raw = Buffer.from('city OFFMARK');
    assert.deepEqual(failing(run), ['off: marker absent from every request body']);
  });

  test('exception message or stack trace on a content-off tool failure fails', () => {
    const run = goodRun((s) => { s[6].events[0].attributes['exception.message'] = 'boom'; });
    assert.ok(failing(run).includes('off: error text, exception message and stack trace are not exported'));
  });

  test('a stack trace in the opt-in phase fails', () => {
    const run = goodRun((s) => { s.find((x) => x.attributes['flue.submission.id'] === 'sub-onerr' && x.events.length)!.events[0].attributes['exception.stacktrace'] = 'at x'; });
    assert.ok(failing(run).includes('on: exception message exported, stack trace dropped'));
  });

  test('missing opt-in content fails', () => {
    const run = goodRun((s) => { delete s.find((x) => x.attributes['gen_ai.tool.call.arguments'])!.attributes['gen_ai.tool.call.arguments']; });
    assert.ok(failing(run).includes('on: marker exported in prompt, tool arguments, tool result and answer'));
  });

  test('compressed requests, a missing header, and a rejected forward fail', () => {
    const run = goodRun();
    (run.requests[0].meta.headers as Record<string, string>)['content-encoding'] = 'gzip';
    delete (run.requests[0].meta.headers as Record<string, string>)['x-secret-key'];
    run.requests[0].meta.forwardStatus = 400;
    assert.deepEqual(failing(run), [
      'no request is compressed',
      'every request carries X-Api-Key and X-Secret-Key',
      'collector accepted every forwarded request',
    ]);
  });

  test('a flat trace fails the hierarchy check', () => {
    const run = goodRun((s) => { s[1].parentSpanId = ''; });
    assert.ok(failing(run).includes('off: chat and execute_tool spans are children of the root'));
  });
});
