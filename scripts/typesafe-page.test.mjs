import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { integrations } from '../src/lib/integrations.mjs';

const read = file => readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/traceai/typesafe.mdx');
const app = read('examples/traceai/typesafe/app.py');
const python = [...page.matchAll(/```python\n([\s\S]*?)```/g)].map(match => match[1].trim());

function excerpt(name) {
  const match = app.match(new RegExp(`# --- ${name} start ---\\n([\\s\\S]*?)\\s*# --- ${name} end ---`));
  assert.ok(match, `Missing app.py excerpt: ${name}`);
  const lines = match[1].split('\n');
  const indent = Math.min(...lines.filter(line => line.trim()).map(line => line.match(/^ */)[0].length));
  return lines.map(line => line.slice(indent)).join('\n').trim();
}

test('TypeSafe snippets are exact excerpts of the runnable example', () => {
  for (const name of ['recipe', 'questions', 'sync call', 'async call']) {
    assert.ok(python.includes(excerpt(name)), `Page snippet differs from app.py: ${name}`);
  }
});

test('TypeSafe snippets define the ticket and use no example-only variables', () => {
  const questions = python.find(block => block.includes('QUESTIONS = {'));
  assert.ok(questions?.startsWith('TICKET = ('), 'Define TICKET with the questions');
  assert.doesNotMatch(page, /\bMARKER\b|RUN_MARKER/);
  assert.ok(page.indexOf('TICKET = (') < page.indexOf('state=TICKET'));
});

test('TypeSafe states the released package Python range', () => {
  assert.match(page, /pip install traceAI-typesafe typesafe-sdk/);
  assert.match(page, /Python 3\.10 to 3\.13, as required by `traceAI-typesafe` 0\.1\.0/);
  assert.match(page, /`typesafe-sdk` 0\.7\.0 or later, below 1\.0/);
  assert.doesNotMatch(page, /fi-instrumentation-otel does not support/);
});

test('TypeSafe page keeps engineering evidence out of the setup guide', () => {
  assert.doesNotMatch(page, /STANDIN|stand-in|run_e2e\.sh|Live vendor verification|verified|fi_verify|rows_hit|TH-\d+|20\d\d-\d\d-\d\d/i);
  assert.doesNotMatch(page, /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/);
  assert.match(page, /FI_HIDE_INPUTS=true/);
  assert.match(page, /never turns answers into Pass\/Fail/);
});

test('TypeSafe is discoverable as a traceAI model-provider guide', () => {
  const entry = integrations.find(item => item.id === 'typesafe');
  assert.equal(entry?.href, '/docs/integrations/traceai/typesafe');
  assert.equal(entry.category, 'providers');
  assert.equal(entry.method, 'traceAI SDK');
});
