import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = readFileSync(new URL('../src/pages/docs/integrations/traceai/langchain-deep-agents.mdx', import.meta.url), 'utf8');

test('Deep Agents is discoverable as a maintained LangChain integration', () => {
  const entry = integrations.find(item => item.id === 'langchain-deep-agents');
  assert.equal(entry?.href, '/docs/integrations/traceai/langchain-deep-agents');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'traceAI SDK');
  assert.equal(entry?.logo, 'langchain');
  assert.match(page, /from traceai_langchain import LangChainInstrumentor/);
  assert.doesNotMatch(page, /pip install[^\n]*traceAI-deepagents/);
});

test('Deep Agents setup uses released pins and the correct Python and core requirements', () => {
  for (const pin of [
    'traceAI-langchain==0.2.1',
    'fi-instrumentation-otel==1.2.3',
    'deepagents==0.7.28',
    'langchain-openai==1.7.4',
  ]) assert.ok(page.includes(pin), `Missing released dependency: ${pin}`);
  assert.match(page, /Python 3\.11–3\.13/);
  assert.match(page, /Deep Agents 0\.7\.28 requires `langchain-core>=1\.6\.11`/);
  assert.match(page, /model adapter may require a newer core/);
  assert.doesNotMatch(page, /1\.6\.6|latest stable|before its release/);
});

test('Deep Agents instruments before construction and flushes after failed calls', () => {
  const example = page.match(/```python\n([\s\S]*?)```/)?.[1];
  assert.ok(example, 'Keep a runnable Python application example');
  const register = example.indexOf('trace_provider = register(');
  const instrument = example.indexOf('LangChainInstrumentor().instrument(');
  const create = example.indexOf('agent = create_deep_agent(');
  assert.ok(register >= 0 && register < instrument && instrument < create);
  assert.match(example, /model=ChatOpenAI\(model=/);
  assert.match(example, /backend=StateBackend\(\)/);
  assert.match(example, /config=\{"configurable": \{"thread_id": "trip-42"\}\}/);
  assert.match(example, /try:\n[\s\S]*agent\.invoke\([\s\S]*finally:\n\s+trace_provider\.force_flush\(\)/);
  assert.match(page, /does not persist agent state between invocations without a checkpointer/);
  assert.match(page, /Open \*\*Observe\*\*, select \*\*deep-agents-app\*\*/);
});

test('Deep Agents privacy distinguishes exception events from status descriptions', () => {
  const setup = page.split('## 3. Instrument')[0];
  for (const setting of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_ERROR_DETAILS']) {
    assert.ok(setup.includes(`export ${setting}=true`), `Configure ${setting} before starting the agent`);
  }
  const privacy = page.split('## Privacy')[1]?.split('## Troubleshooting')[0];
  assert.ok(privacy, 'Keep the privacy guidance');
  assert.match(privacy, /from fi_instrumentation import TraceConfig/);
  for (const option of ['hide_inputs', 'hide_outputs', 'hide_error_details']) {
    assert.ok(privacy.includes(`${option}=True`));
  }
  assert.match(privacy, /replace the earlier `instrument\(\)` call/);
  assert.match(privacy, /status description contains the exception message without the formatted traceback/);
  assert.match(privacy, /`exception` event can contain both the message and a stack trace/);
  assert.match(privacy, /removes error messages, stack traces and the status description while preserving `ERROR` status and exception types/);
  assert.match(privacy, /An explicit `false` overrides that derivation/);
  assert.match(privacy, /not a general-purpose metadata scrubber/);
  assert.doesNotMatch(page, /never a stack trace|no longer exports a stack trace/);
});

test('Deep Agents guide keeps customer instructions separate from verification history', () => {
  assert.doesNotMatch(page, /Tested versions|Reference run|Verified by scanning|privacy scan|local Future AGI stack|\b2026-\d{2}-\d{2}\b/i);
  assert.doesNotMatch(page, /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i);
  assert.match(page, /Python `create_deep_agent` application API, not Deep Agents JavaScript, CLI or ACP sessions/);
});
