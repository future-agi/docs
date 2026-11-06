import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = file => readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
const page = read('src/pages/docs/integrations/traceai/go/eino.mdx');
const readme = read('examples/traceai/eino-go/README.md');
const main = read('examples/traceai/eino-go/main.go');
const dependencies = [
  'go get github.com/future-agi/traceAI/go/eino@v0.1.0 github.com/cloudwego/eino@v0.9.21',
  'go get github.com/cloudwego/eino-ext/components/model/openai@v0.1.13',
  'go get go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0',
];
const bash = text => [...text.matchAll(/```bash\n([\s\S]*?)```/g)].map(match => match[1]).join('\n');

function inOrder(text, commands) {
  let previous = -1;
  for (const command of commands) {
    const index = text.indexOf(command);
    assert.ok(index > previous, `Missing or out-of-order setup command: ${command}`);
    previous = index;
  }
}

test('Eino example starts from a new directory with source, module and pinned dependencies', () => {
  inOrder(bash(page), [
    'mkdir eino-go-example',
    'cd eino-go-example',
    'go mod init example.com/eino-go-example',
    'curl --fail --location --output main.go',
    'https://raw.githubusercontent.com/future-agi/traceAI/go/eino/v0.1.0/go/eino/example/main.go',
    ...dependencies,
    'go mod tidy',
    'export FI_API_KEY=',
    'export FI_SECRET_KEY=',
    'export FI_PROJECT_NAME=',
    'export OPENAI_API_KEY=',
    'go run . -stream -fail',
  ]);
  assert.match(page, /Steps 3–6 explain the tracing already included in `main\.go`/);
  assert.match(page, /from the same `eino-go-example` directory/);
  assert.doesNotMatch(page, /run_e2e\.sh/);
});

test('Eino checkout instructions initialize the linked example without the QA runner', () => {
  inOrder(bash(readme), [
    'cd examples/traceai/eino-go',
    'go mod init example.com/eino-go-example',
    ...dependencies,
    'go mod tidy',
    'export FI_API_KEY=',
    'export FI_SECRET_KEY=',
    'export FI_PROJECT_NAME=',
    'export OPENAI_API_KEY=',
    'go run . -stream -fail',
  ]);
  assert.match(main, /package main/);
  assert.match(main, /func main\(\)/);
  assert.doesNotMatch(main, /go run \.\/example/);
  assert.doesNotMatch(readme, /run_e2e\.sh|MARK_DEFAULT|MARK_HIDDEN/);
});

test('Eino identity attributes distinguish always-present kind from conditional metadata', () => {
  const captured = page.split('## What is captured')[1]?.split('## Privacy')[0];
  assert.ok(captured, 'Keep the captured attribute reference');
  assert.match(captured, /^\| `gen_ai\.span\.kind` \| always \|$/m);
  assert.match(captured, /^\| `gen_ai\.operation\.name` \| only on LLM \(`chat`\), tool \(`execute_tool`\), embedding \(`embeddings`\) and agent \(`invoke_agent`\) spans \|$/m);
  assert.match(captured, /^\| `eino\.component`, `eino\.type`, `eino\.name` \| only when `RunInfo` supplies the corresponding non-empty field \|$/m);
});

test('Eino text switches do not hide ordinary conversation value attributes', () => {
  const privacy = page.split('## Privacy')[1]?.split('## Errors')[0];
  assert.ok(privacy, 'Keep the customer-facing privacy section');
  const textSwitches = privacy.split('\n').find(line => line.startsWith('| `FI_HIDE_INPUT_TEXT`, `FI_HIDE_OUTPUT_TEXT` |'));
  assert.ok(textSwitches, 'Keep the text-specific masking settings');
  assert.match(textSwitches, /redact text only in the structured `gen_ai\.input\.messages\.\*` \/ `gen_ai\.output\.messages\.\*` attributes/);
  assert.match(textSwitches, /keep roles and tool calls/);
  assert.match(textSwitches, /do not redact `input\.value` \/ `output\.value`/);
  const warning = privacy.split('\n\n').find(paragraph => paragraph.startsWith('Message-specific switches do not redact'));
  assert.ok(warning, 'Explain the value-attribute boundary beyond Agentic or generic JSON');
  assert.match(warning, /`input\.value` \/ `output\.value`/);
  assert.match(warning, /conversation text for ordinary `schema\.Message` inputs and `ChatModelAgent` runs/);
  assert.match(warning, /not just Agentic or generic JSON payloads/);
  assert.match(warning, /Set \*\*`FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true`\*\* to keep conversation text out of these values and the structured message attributes/);
});

test('Eino media exclusions apply only to structured message media fields', () => {
  const privacy = page.split('## Privacy')[1]?.split('## Errors')[0];
  assert.ok(privacy, 'Keep the customer-facing privacy section');
  assert.match(privacy, /Structured `schema\.Message` capture excludes audio, video and file data from the dedicated media fields/);
  assert.match(privacy, /does not inspect data embedded in message text or tool arguments/);
  assert.match(privacy, /`AgenticModel`, `AgenticAgent` and other generic JSON payloads can include inline media data/);
  assert.match(privacy, /base64 audio, video and files/);
  assert.match(privacy, /extra fields in `input\.value` \/ `output\.value`/);
  assert.match(privacy, /Set \*\*`FI_HIDE_INPUTS=true` and `FI_HIDE_OUTPUTS=true`\*\* when those payloads must not leave the process/);
  assert.match(privacy, /32 000-byte limit on JSON values truncates content; it is not redaction/);
  assert.doesNotMatch(privacy, /In every mode:|credentials and component configuration are never copied/);
});

test('Eino message-specific masking is not described as generic JSON sanitization', () => {
  const warning = page.split('\n\n').find(paragraph => paragraph.startsWith('`AgenticModel`, `AgenticAgent` and other generic JSON'));
  assert.ok(warning, 'Keep the generic JSON boundary next to the privacy settings');
  for (const name of [
    'FI_HIDE_INPUT_MESSAGES', 'FI_HIDE_OUTPUT_MESSAGES', 'FI_HIDE_INPUT_TEXT',
    'FI_HIDE_OUTPUT_TEXT', 'FI_HIDE_INPUT_IMAGES', 'FI_BASE64_IMAGE_MAX_LENGTH',
  ]) assert.ok(warning.includes(`\`${name}\``), name);
  assert.match(warning, /do not sanitize generic JSON/);
  assert.match(readme, /Message-specific switches do not sanitize Agentic or generic JSON/);
});
