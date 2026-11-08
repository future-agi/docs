// Execute every fenced block in the guide against published npm packages.
// Run only in a disposable E2B sandbox or CI. No real service credentials needed.
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createServer } from 'node:http';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { gunzipSync } from 'node:zlib';

const exec = promisify(execFile);
const page = await readFile(new URL('../src/pages/docs/integrations/traceai/auto.mdx', import.meta.url), 'utf8');
const blocks = [...page.matchAll(/```(bash|javascript)\n([\s\S]*?)\n```/g)].map((m, index) => ({ index, language: m[1], code: m[2] }));
assert.equal(blocks.length, 10, 'Every new fenced block needs an execution case');
const block = prefix => {
  const found = blocks.find(b => b.code.startsWith(prefix));
  assert.ok(found, prefix);
  return found;
};
const done = new Set();
const results = [];
const batches = [];
const requests = [];
const errors = [];
let collectorStatus = 200;
const app = await mkdtemp(join(tmpdir(), 'auto-docs-'));
const output = resolve(process.env.AUTO_EVIDENCE_DIR || '/tmp/docs-auto-evidence');
await mkdir(output, { recursive: true });
const server = createServer(async (req, res) => {
  try {
    const parts = [];
    for await (const part of req) parts.push(part);
    let raw = Buffer.concat(parts);
    if (req.headers['content-encoding'] === 'gzip') raw = gunzipSync(raw);
    const data = JSON.parse(raw.toString() || '{}');
    if (req.url === '/v1/chat/completions') {
      assert.equal(req.headers.authorization, 'Bearer synthetic-provider-key');
      assert.equal(data.model, 'docs-test-model');
      assert.equal(data.messages[0].content, 'Say hello in one word.');
      requests.push(data);
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ id: 'chatcmpl-docs', object: 'chat.completion', created: 1700000000, model: data.model, choices: [{ index: 0, message: { role: 'assistant', content: 'Hello!' }, finish_reason: 'stop' }], usage: { prompt_tokens: 13, completion_tokens: 3, total_tokens: 16 } }));
    } else if (req.url === '/tracer/v1/traces') {
      assert.equal(req.headers['x-api-key'], 'synthetic-fi-api-key');
      assert.equal(req.headers['x-secret-key'], 'synthetic-fi-secret-key');
      batches.push(data);
      res.writeHead(collectorStatus, { 'content-type': 'application/json' });
      res.end('{}');
    } else {
      throw new Error(`Unexpected request route: ${req.url}`);
    }
  } catch (error) {
    errors.push(error.message);
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end('{}');
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}`;
// Do not inherit FI credentials, provider keys, preload flags or user profiles.
const env = {
  PATH: process.env.PATH,
  HOME: join(app, 'home'),
  XDG_CONFIG_HOME: join(app, 'config'),
  FI_BASE_URL: url,
  OPENAI_BASE_URL: `${url}/v1`,
  OPENAI_API_KEY: 'synthetic-provider-key',
  OPENAI_MODEL: 'docs-test-model',
  npm_config_registry: 'https://registry.npmjs.org',
  npm_config_update_notifier: 'false',
  npm_config_audit: 'false',
  npm_config_fund: 'false',
};
const setup = block('export FI_API_KEY');
const config = setup.code.replaceAll('your-api-key', 'synthetic-fi-api-key').replaceAll('your-secret-key', 'synthetic-fi-secret-key');
const allSpans = from => batches.slice(from).flatMap(batch => batch.resourceSpans.flatMap(resource => resource.scopeSpans.flatMap(scope => scope.spans)));
async function run(name, command, { expected = 'model', hidden = false, overrides = {} } = {}) {
  const from = batches.length;
  const before = requests.length;
  const result = await exec('bash', ['-c', `set -euo pipefail\n${config}\n${command}`], { cwd: app, env: { ...env, ...overrides }, timeout: 180000, maxBuffer: 4 * 1024 * 1024 });
  const spans = allSpans(from);
  assert.deepEqual(errors, []);
  if (expected === 'model') {
    assert.equal(requests.length - before, 1, `${name}: provider calls`);
    assert.match(result.stdout, /Hello!/);
    assert.equal(spans.length, 1, `${name}: exactly one model span, no duplicate wire span`);
    const serialized = JSON.stringify(spans);
    const attributes = Object.fromEntries(spans[0].attributes.map(attribute => [attribute.key, attribute.value]));
    assert.equal(attributes['gen_ai.request.model'].stringValue, 'docs-test-model');
    assert.equal(Number(attributes['gen_ai.usage.input_tokens'].intValue), 13);
    assert.equal(Number(attributes['gen_ai.usage.output_tokens'].intValue), 3);
    assert.equal(Number(attributes['gen_ai.usage.total_tokens'].intValue), 16);
    assert.ok(BigInt(spans[0].endTimeUnixNano) > BigInt(spans[0].startTimeUnixNano));
    assert.match(JSON.stringify(batches.slice(from)), /my-ai-app/);
    if (hidden) assert.doesNotMatch(serialized, /Say hello in one word\.|Hello!/);
    else { assert.match(serialized, /Say hello in one word\./); assert.match(serialized, /Hello!/); }
    assert.doesNotMatch(serialized, /synthetic-(?:fi|provider)/);
  } else if (expected === 'doctor') {
    const report = JSON.parse(result.stdout);
    assert.equal(report.active, true);
    assert.equal(report.collector, collectorStatus === 200 ? 'accepted' : 'failed');
    assert.equal(spans.length, 1);
    assert.equal(spans[0].name, 'traceai.auto.doctor');
  } else if (expected === 'bootstrap') {
    const report = JSON.parse(result.stdout);
    assert.ok(report.integrations.some(i => i.name === 'openai' || i.id === 'openai'));
    assert.ok(Array.isArray(report.install));
    assert.equal(spans.length, 0);
  }
  results.push({ name, spans: spans.length, providerCalls: requests.length - before, exitCode: 0 });
  console.log(JSON.stringify(results.at(-1)));
  return result;
}
async function execute(prefix, options) {
  const selected = block(prefix);
  done.add(selected.index);
  return run(prefix.split('\n')[0], selected.code, options);
}
try {
  await mkdir(env.HOME, { recursive: true });
  await writeFile(join(app, 'package.json'), JSON.stringify({ name: 'auto-docs-example', private: true, scripts: { start: 'node app.mjs' } }));
  await execute('npm install @traceai/auto', { expected: 'install' });
  await execute('npm install openai', { expected: 'install' });
  const example = block('import OpenAI');
  assert.doesNotMatch(example.code, /traceai|opentelemetry/);
  await writeFile(join(app, 'app.mjs'), example.code);
  // The CommonJS startup variant uses an equivalent normal application, no tracing imports.
  await writeFile(join(app, 'app.cjs'), `const OpenAI = require('openai');\n(async () => {\n${example.code.split('\n').slice(1).join('\n')}\n})().catch(error => { console.error(error); process.exitCode = 1; });\n`);
  done.add(example.index);
  done.add(setup.index); // Executed before every shell command with synthetic substitutions.
  await execute('node --import');
  await execute('NODE_OPTIONS=');
  await execute('node --require');
  await execute('npx --no-install traceai-auto bootstrap', { expected: 'bootstrap' });
  await execute('FI_HIDE_INPUTS=', { hidden: true });
  await execute('npx --no-install traceai-auto doctor', { expected: 'doctor' });
  // Regression: doctor exit code can be zero even when collection fails.
  collectorStatus = 400;
  await run('doctor rejects collector errors despite exit zero', block('npx --no-install traceai-auto doctor').code, { expected: 'doctor' });
  collectorStatus = 200;
  assert.equal(done.size, blocks.length, 'All page blocks executed');
  const packages = {};
  for (const name of ['@traceai/auto', 'openai']) packages[name] = JSON.parse(await readFile(join(app, 'node_modules', name, 'package.json'), 'utf8')).version;
  const receipt = { node: process.version, packages, executedBlocks: done.size, totalBlocks: blocks.length, results, scope: 'Synthetic loopback provider and OTLP only; not a live Cloud test.' };
  await writeFile(join(output, 'snippets.json'), JSON.stringify(receipt, null, 2));
  await writeFile(join(output, 'otlp.json'), JSON.stringify(batches, null, 2));
  await writeFile(join(output, 'package-lock.json'), await readFile(join(app, 'package-lock.json')));
  console.log(JSON.stringify(receipt));
} finally {
  await new Promise(resolve => server.close(resolve));
  await rm(app, { recursive: true, force: true });
}
