import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/traceai/parallel.mdx', import.meta.url), 'utf8');

test('Parallel guide uses released packages and the shared integration catalog', () => {
  const entry = integrations.find(item => item.id === 'parallel');
  assert.equal(entry?.href, '/docs/integrations/traceai/parallel');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI SDK');
  for (const pin of ['traceAI-parallel==0.1.1', 'fi-instrumentation-otel==1.2.3', 'parallel-web==1.3.5']) {
    assert.ok(page.includes(pin), pin);
  }
  assert.match(page, /Task runs, task groups, FindAll and Monitor are not traced/);
  assert.match(page, /Open \*\*Observe\*\*/);
  assert.doesNotMatch(page, /Live vendor verification|Tested versions|verified live|STANDIN|\bAlpha\b|2026-10-17/i);
});

test('Parallel guide preserves privacy controls and raw-response limitations', () => {
  for (const flag of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS']) {
    assert.ok(page.includes(`export ${flag}=true`), flag);
  }
  assert.match(page, /before initializing the instrumentor/);
  assert.match(page, /verbatim matches only, not escaped or truncated copies/);
  assert.match(page, /response bodies are not parsed for result counts or IDs/);
  assert.match(page, /streaming spans end when response headers arrive/);
});

test('Parallel example skips extraction for empty results and flushes on success or errors', () => {
  const example = page.match(/```python\n([\s\S]*?)\n```/)?.[1];
  assert.ok(example, 'Keep one complete runnable Python example');
  // Execute the documented control flow with stub clients, never vendor calls.
  const harness = String.raw`
import contextlib
import io
import sys
import types

source = sys.stdin.read()
code = compile(source, 'parallel_example.py', 'exec')

for scenario in ('empty', 'hit', 'search_error', 'extract_error'):
    calls = []
    provider = types.SimpleNamespace(force_flush=lambda: calls.append('flush'))
    def register(**kwargs):
        assert kwargs == dict(project_type='observe', project_name='parallel-search')
        calls.append('register')
        return provider
    class Instrumentor:
        def instrument(self, *, tracer_provider):
            assert tracer_provider is provider
            calls.append('instrument')
    class Parallel:
        def __enter__(self):
            assert calls == ['register', 'instrument']
            return self
        def __exit__(self, *args):
            calls.append('close')
        def search(self, *, search_queries, mode):
            assert search_queries and mode == 'turbo'
            calls.append('search')
            if scenario == 'search_error':
                raise RuntimeError('search failed')
            results = [] if scenario == 'empty' else [types.SimpleNamespace(url='https://example.com')]
            return types.SimpleNamespace(results=results, session_id='example-session')
        def extract(self, *, urls, session_id):
            assert urls == ['https://example.com']
            assert session_id == 'example-session'
            calls.append('extract')
            if scenario == 'extract_error':
                raise RuntimeError('extract failed')
            return types.SimpleNamespace(results=[object()])
    modules = {
        'fi_instrumentation': dict(register=register),
        'fi_instrumentation.fi_types': dict(ProjectType=types.SimpleNamespace(OBSERVE='observe')),
        'traceai_parallel': dict(ParallelInstrumentor=Instrumentor),
        'parallel': dict(Parallel=Parallel),
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module
    output = io.StringIO()
    raised = None
    with contextlib.redirect_stdout(output):
        try:
            exec(code, {})
        except RuntimeError as error:
            raised = str(error)
    expected_error = scenario.replace('_error', ' failed') if scenario.endswith('_error') else None
    assert raised == expected_error, (scenario, raised)
    operations = ['search'] if scenario in ('empty', 'search_error') else ['search', 'extract']
    assert calls == ['register', 'instrument', *operations, 'close', 'flush'], (scenario, calls)
    if scenario == 'empty':
        assert 'No search results' in output.getvalue()
    elif scenario == 'hit':
        assert 'Extracted 1 page(s).' in output.getvalue()
`;
  const result = spawnSync('python3', ['-I', '-c', harness], { input: example, encoding: 'utf8' });
  assert.equal(result.status, 0, result.error?.message || result.stdout + result.stderr);
});
