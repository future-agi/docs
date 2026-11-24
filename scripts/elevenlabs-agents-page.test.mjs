import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const page = fs.readFileSync(new URL('../src/pages/docs/integrations/traceai/elevenlabs-agents.mdx', import.meta.url), 'utf8');

test('ElevenLabs Agents uses the released forwarder and shared voice catalog', () => {
  const entry = integrations.find(item => item.id === 'elevenlabs-agents');
  assert.equal(entry?.href, '/docs/integrations/traceai/elevenlabs-agents');
  assert.equal(entry?.category, 'voice');
  assert.equal(entry?.method, 'traceAI forwarder');
  assert.match(page, /Python 3\.10–3\.13/);
  assert.match(page, /pip install "traceAI-elevenlabs-agents==0\.1\.0"/);
  assert.match(page, /traceai-elevenlabs-agents serve --host 0\.0\.0\.0 --port 8787/);
  assert.match(page, /does not send them directly to an OTLP collector/);
  assert.doesNotMatch(page, /pip install[^\n]*git\+|copy[^\n]*(?:exporter|bridge|helper)/i);
});

test('ElevenLabs setup retains authenticated delivery and privacy before startup', () => {
  const setup = page.split('## 3. Run the forwarder')[0];
  for (const variable of ['ELEVENLABS_WEBHOOK_SECRET', 'FI_API_KEY', 'FI_SECRET_KEY', 'FI_PROJECT_NAME', 'FI_ELEVENLABS_STATE_PATH']) {
    assert.ok(setup.includes(`export ${variable}=`), variable);
  }
  assert.match(setup, /HMAC authentication/);
  assert.match(setup, /Conversation content is captured by default/);
  assert.match(setup, /export FI_HIDE_INPUTS=true FI_HIDE_OUTPUTS=true/);
  assert.match(setup, /\/tracer\/v1\/traces/);
  assert.match(page, /raw body and `ElevenLabs-Signature` header/);
  assert.match(page, /20 MiB/);
  assert.match(page, /OpenTelemetry transcript payloads/);
});

test('ElevenLabs backfill and retries preserve duplicate and delivery limitations', () => {
  assert.match(page, /CONVAI_READ/);
  assert.match(page, /traceai-elevenlabs-agents backfill --conversation-id "<conversation-id>"/);
  assert.match(page, /format=opentelemetry/);
  assert.match(page, /same Future AGI configuration and `FI_ELEVENLABS_STATE_PATH`/);
  assert.match(page, /Keep this file across restarts/);
  assert.match(page, /Do not run independent replicas with separate records/);
  assert.match(page, /not an exactly-once delivery guarantee/);
  assert.match(page, /response is lost/);
  assert.match(page, /up to five times, but not other `4xx`/);
  assert.match(page, /backfill --force` only after confirming/);
  assert.doesNotMatch(page, /retry after any failure is safe/);
});

test('ElevenLabs retains privacy, passed-through status and post-call scope', () => {
  for (const setting of ['FI_HIDE_INPUTS', 'FI_HIDE_OUTPUTS', 'FI_HIDE_INPUT_MESSAGES', 'FI_HIDE_OUTPUT_MESSAGES', 'FI_HIDE_INPUT_TEXT', 'FI_HIDE_OUTPUT_TEXT', 'FI_PII_REDACTION']) {
    assert.ok(page.includes(`\`${setting}\``), setting);
  }
  assert.match(page, /removes the combined transcript/);
  assert.match(page, /status and exception messages/);
  assert.match(page, /Status is passed through, not inferred/);
  assert.match(page, /failed tool or interrupted call can arrive with status OK/);
  assert.match(page, /does not consume the monitoring WebSocket or `post_call_audio`/);
  assert.match(page, /not both/);
});

test('ElevenLabs guide contains setup instructions rather than a verification diary', () => {
  assert.doesNotMatch(page, /\balpha\b|stand-?in|live (?:vendor|webhook) verification|fi_verify|BLOCKED-ON|2026-10-\d{2}/i);
  assert.doesNotMatch(page, /\b[a-f0-9]{32}\b/);
  assert.doesNotMatch(page, /\/Users\/|\/Volumes\//);
});
