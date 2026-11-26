import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spawnSync } from 'node:child_process';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/traceai/google_genai_live.mdx', import.meta.url), 'utf8');
const pythonBlocks = [...page.matchAll(/```python\n([\s\S]*?)\n```/g)].map(match => match[1]);

test('Gemini Live is discoverable as a maintained Python voice integration', () => {
  const entry = integrations.find(item => item.id === 'google-genai-live');
  assert.equal(entry?.href, '/docs/integrations/traceai/google_genai_live');
  assert.equal(entry?.category, 'voice');
  assert.equal(entry?.method, 'traceAI SDK');
  assert.equal(entry?.logo, 'google');
  for (const requirement of [
    'Python 3.10–3.13', 'google-genai>=2.28,<3',
    'traceAI-google-genai-live==0.1.0', 'google-genai==2.31.0',
    'fi-instrumentation-otel==1.2.3', 'GEMINI_LIVE_MODEL',
  ]) assert.ok(page.includes(requirement), requirement);
  assert.match(page, /not Vertex AI Live or ephemeral-token clients/);
  assert.match(page, /does not instrument `google-genai` 3\.x/);
});

test('Gemini Live example configures tracing before connecting and consumes one turn', () => {
  const sample = pythonBlocks[0];
  assert.ok(sample, 'Provide a complete Python application example');
  for (const code of [
    'from fi_instrumentation import register',
    'from fi_instrumentation.fi_types import ProjectType',
    'from traceai_google_genai_live import instrument',
    'project_type=ProjectType.OBSERVE',
    'model=os.environ["GEMINI_LIVE_MODEL"]',
    '"response_modalities": ["AUDIO"]',
    '"output_audio_transcription": {}',
    'turn_complete=True',
    'async for message in session.receive():',
    'asyncio.wait_for(main(), timeout=60)',
    'finally:\n    trace_provider.force_flush()',
  ]) assert.ok(sample.includes(code), code);
  assert.ok(sample.indexOf('trace_provider = register(') < sample.indexOf('instrument(tracer_provider=trace_provider)'));
  assert.ok(sample.indexOf('instrument(tracer_provider=trace_provider)') < sample.indexOf('client.aio.live.connect('));
  assert.doesNotMatch(sample, /range\(2\)/);
  for (const block of pythonBlocks) {
    const parsed = spawnSync('python3', ['-I', '-c', 'import ast, sys; ast.parse(sys.stdin.read())'], { input: block, encoding: 'utf8' });
    assert.equal(parsed.status, 0, parsed.stderr || String(parsed.error || 'Python snippet did not parse'));
  }
});

test('Gemini Live retains privacy and reconnect guidance without a verification diary', () => {
  const beforeExample = page.split('## Run a session')[0];
  assert.match(beforeExample, /Text content is captured by default/);
  assert.match(beforeExample, /export FI_HIDE_INPUTS=true/);
  assert.match(beforeExample, /export FI_HIDE_OUTPUTS=true/);
  assert.match(page, /TraceConfig\(hide_inputs=True, hide_outputs=True\)/);
  assert.match(page, /not your application logs or custom span attributes/);
  assert.match(page, /does not attach audio recordings/);
  assert.match(page, /instrumentor does not reconnect for you/);
  assert.match(page, /resume_window_seconds` \(default 30\)/);
  assert.match(page, /resumable handle/);
  assert.match(page, /Open \*\*Observe\*\*, select \*\*my-voice-agent\*\*/);
  assert.doesNotMatch(page, /fi_verify|run_e2e|verified on|tested sessions|twelve gates|stored columns|\balpha\b|\b20\d{2}-\d{2}-\d{2}\b/i);
});
