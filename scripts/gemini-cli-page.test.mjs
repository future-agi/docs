import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const read = file => fs.readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/coding-agents/gemini-cli.mdx');
const collector = read('examples/coding-agents/gemini-cli/otel-collector.yaml');
const settings = JSON.parse(read('examples/coding-agents/gemini-cli/settings.json'));

test('Gemini CLI is discoverable as native OTLP with explicit non-sandbox scope', () => {
  const entry = integrations.find(item => item.id === 'gemini-cli');
  assert.equal(entry?.href, '/docs/integrations/coding-agents/gemini-cli');
  assert.equal(entry.category, 'coding');
  assert.equal(entry.method, 'Native OTLP');
  const prerequisites = page.split('## 1. Start the collector')[0];
  assert.match(prerequisites, /Gemini CLI 0\.64\.0 on macOS/);
  assert.match(prerequisites, /non-sandbox interactive \(`gemini`\) and non-interactive \(`gemini -p`\) sessions/);
  assert.match(prerequisites, /does not cover sandbox runtimes/);
  assert.match(prerequisites, /@google\/gemini-cli@0\.64\.0/);
  assert.match(prerequisites, /releases\/tag\/v0\.162\.0/);
  assert.doesNotMatch(page, /run_e2e\.sh|CAPTURE_CONTENT|test_collector\.py|in our test|not tested|read 2026-|verified live/i);
});

test('Gemini CLI setup matches the shipped native settings and preserves privacy controls', () => {
  const snippet = page.match(/```json\n([\s\S]*?)\n```/);
  assert.ok(snippet, 'Include a complete telemetry settings example');
  assert.deepEqual(JSON.parse(snippet[1]), settings);
  assert.equal(settings.telemetry.logPrompts, false);
  assert.equal(settings.telemetry.traces, true);
  assert.equal(settings.telemetry.otlpProtocol, 'http');
  assert.match(collector, /processors: \[transform\/gemini-cli, transform\/strip-content, batch\]/);
  assert.match(collector, /compression: none/);
  assert.match(collector, /endpoint: \$\{env:GEMINI_OTLP_LISTEN:-127\.0\.0\.1:4318\}/);
  for (const key of [
    'gen_ai.input.messages', 'gen_ai.output.messages', 'input.value', 'output.value',
    'gen_ai.system_instructions', 'gen_ai.tool.definitions', 'exception.stacktrace',
    'exception.message', 'process.command_args', 'process.command',
    'process.executable.path', 'process.executable.name', 'process.owner', 'host.name', 'host.id',
  ]) assert.ok(collector.includes(`delete_key(attributes, "${key}")`), `Preserve filtering for ${key}`);
  assert.match(page, /local collector receives attributes before filtering/);
  assert.match(page, /Tool descriptions can come from your MCP servers/);
  assert.match(page, /remove sensitive text from tool names and descriptions/i);
  assert.match(page, /This also exports system instructions, `GEMINI\.md` memory, tool schemas and full error messages/);
  assert.match(page, /Stack traces and the local identity resource fields remain removed/);
  assert.match(page, /processors: \[transform\/gemini-cli, batch\]/);
});

test('Gemini CLI explains session mapping and native trace limitations', () => {
  assert.match(page, /copies `gen_ai\.conversation\.id` to `session\.id`/);
  assert.match(page, /does not emit turn spans in this mode/);
  assert.match(page, /returns an error instead of throwing/);
  assert.match(page, /status `OK`/);
  assert.match(page, /Gemini CLI has no whole-session span/);
  assert.match(page, /Logs and metrics are not forwarded/);
  assert.match(collector, /set\(attributes\["session.id"\], attributes\["gen_ai.conversation.id"\]\)/);
  for (const operation of ['user_prompt', 'system_prompt', 'schedule_tool_calls']) {
    assert.ok(collector.includes(`set(attributes["gen_ai.span.kind"], "CHAIN") where attributes["gen_ai.operation.name"] == "${operation}"`));
  }
});
