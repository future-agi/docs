import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/traceai/semantic-kernel.mdx', import.meta.url), 'utf8');

test('Semantic Kernel Python is discoverable as a native-diagnostics adapter', () => {
  const entry = integrations.find(item => item.id === 'semantic-kernel-python');
  assert.equal(entry?.href, '/docs/integrations/traceai/semantic-kernel');
  assert.equal(entry?.category, 'frameworks');
  assert.equal(entry?.method, 'Native OTel + traceAI');
  assert.match(page, /native OpenTelemetry diagnostics/);
  assert.doesNotMatch(page, /## Tested versions|verified live|63 tests|latest stable|\bAlpha\b/i);
});

test('Semantic Kernel quickstart is a standalone async agent with a real connector and tool', () => {
  for (const dependency of ['traceAI-semantic-kernel==0.1.2', 'fi-instrumentation-otel==1.2.3', 'semantic-kernel==1.45.0']) {
    assert.ok(page.includes(dependency), dependency);
  }
  for (const variable of ['FI_API_KEY', 'FI_SECRET_KEY', 'OPENAI_API_KEY', 'OPENAI_CHAT_MODEL_ID']) {
    assert.ok(page.includes(`export ${variable}=`), variable);
  }
  const blocks = [...page.matchAll(/```python\n([\s\S]*?)\n```/g)].map(match => match[1]);
  assert.equal(blocks.length, 1, 'Keep one complete application example');
  const example = blocks[0];
  const syntax = spawnSync('python3', ['-I', '-c', 'import sys; compile(sys.stdin.read(), "semantic_kernel_app.py", "exec")'], {
    input: example,
    encoding: 'utf8',
  });
  assert.equal(syntax.status, 0, syntax.stderr || String(syntax.error || 'Python compilation failed'));
  for (const line of [
    'from semantic_kernel.agents import ChatCompletionAgent',
    'from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion',
    'from semantic_kernel.functions import kernel_function',
    'async def main():',
    'agent = ChatCompletionAgent(',
    'service=OpenAIChatCompletion(',
    'ai_model_id=os.environ["OPENAI_CHAT_MODEL_ID"]',
    'api_key=os.environ["OPENAI_API_KEY"]',
    'plugins={"Hotel": HotelPlugin()}',
    'with using_session("hotel-conversation"):',
    'response = await agent.get_response(',
    'print(response.message.content)',
    'sensitive=False',
    'asyncio.run(main())',
  ]) assert.ok(example.includes(line), line);
  assert.match(example, /finally:\n\s+trace_provider\.force_flush\(\)\n\s+trace_provider\.shutdown\(\)/);
  assert.match(page, /python semantic_kernel_app\.py/);
  assert.match(page, /Open \*\*Observe\*\*/);
});

test('Semantic Kernel keeps Azure AI Inference exclusions before setup', () => {
  const prerequisites = page.split('## Install')[0];
  for (const boundary of [
    '`OpenAIChatCompletion`', '`AzureChatCompletion`',
    '`AzureAIInferenceChatCompletion` is not supported',
    'outside this adapter\'s content and privacy controls',
    'Do not enable `SEMANTICKERNEL_EXPERIMENTAL_GENAI_*` flags as a workaround',
    '`sensitive=False`', '`FI_HIDE_INPUTS`', '`FI_HIDE_OUTPUTS`',
    'not a replacement for an Azure AI Inference endpoint',
  ]) assert.ok(prerequisites.includes(boundary), boundary);
});

test('Semantic Kernel uses released processor behavior and avoids duplicate model instrumentation', () => {
  assert.match(page, /adding a processor to that provider preserves its exporter and the Semantic Kernel mapping processor/);
  assert.match(page, /directly constructed `TracerProvider` still replaces its default processor chain/);
  assert.doesNotMatch(page, /Call `uninstrument\(\)` then `instrument\(\)` again|after any `add_span_processor\(\)`/);
  assert.match(page, /Do not also enable `traceAI-openai`, `traceAI-litellm`/);
});

test('Semantic Kernel privacy distinguishes span filtering, metadata, errors and logs', () => {
  const privacy = page.split('## Content and privacy')[1]?.split('## Troubleshooting')[0];
  assert.ok(privacy);
  for (const boundary of [
    'Semantic Kernel-scoped spans', 'Tool names, descriptions and definitions',
    'exception messages', 'does not change its settings',
    '`FI_HIDE_INPUTS=true`', '`FI_HIDE_OUTPUTS=true`',
    'not other `TraceConfig` settings', 'not independently emitted provider spans',
    'custom attributes or Python logs', 'filters the spans, not those log records',
  ]) assert.ok(privacy.includes(boundary), boundary);
  assert.doesNotMatch(page, /Keep logging from raising the logger level above INFO/);
});
