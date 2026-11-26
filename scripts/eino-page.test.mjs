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

test('Eino error scrubbing is best-effort and does not promise IPv6 privacy', () => {
  const errors = page.split('## Errors')[1]?.split('## Scope limits')[0];
  assert.ok(errors, 'Keep the error export guidance');
  assert.match(errors, /`error\.message` uses the first line of the error with best-effort scrubbing/);
  assert.match(errors, /IPv4 addresses/);
  assert.match(errors, /IPv6 endpoints and other unmatched details can remain/);
  assert.match(errors, /Set \*\*`FI_HIDE_INPUTS=true` or `FI_HIDE_OUTPUTS=true`\*\* to suppress `error\.message` when network details must not be exported/);
  assert.doesNotMatch(errors, /IP addresses|safe to export|all network details.*(?:removed|redacted)/);
});

test('Eino separates top-level callback ordering from nested cross-provider protection', () => {
  const parenting = page.split('### Callback parenting')[1]?.split('## 6. Streams and agents')[0];
  assert.ok(parenting, 'Explain callback parenting next to application spans');
  assert.match(parenting, /A top-level run with no enclosing traceAI run inherits the current OpenTelemetry span/);
  assert.match(parenting, /including one placed on the context by another callback handler/);
  assert.match(parenting, /Eino v0\.9\.21 calls `OnStart` handlers in reverse registration order/);
  assert.match(parenting, /`compose\.WithCallbacks\(h, other\)`, `other` runs first and can make its span the parent/);
  assert.match(parenting, /nested run with an enclosing traceAI span/);
  assert.match(parenting, /current span only if it is valid and uses the same tracer provider/);
  assert.match(parenting, /otherwise it uses the enclosing traceAI span/);
  assert.match(parenting, /not top-level runs or other handlers using the same provider/);
  assert.match(page, /\*\*A traceAI root appears under another tracing handler's span\.\*\*/);
  assert.doesNotMatch(page, /They stay separate|never makes another handler's span the parent/);
});

test('Eino token counts distinguish ordinary usage from positive-only details', () => {
  const captured = page.split('## What is captured')[1]?.split('## Privacy')[0];
  assert.ok(captured, 'Keep the token attribute reference');
  const rows = captured.split('\n');
  const ordinary = rows.find(line => line.startsWith('| `gen_ai.usage.input_tokens`,'));
  const details = rows.find(line => line.startsWith('| `gen_ai.usage.cache_read_tokens`,'));
  assert.ok(ordinary, 'Give ordinary usage its own row');
  assert.ok(details, 'Give cache-read and reasoning counts their own row');
  assert.match(ordinary, /all three are emitted when usage has any non-zero input, output or total count/);
  assert.match(ordinary, /individual input\/output counts may be zero/);
  assert.match(ordinary, /A zero total is derived from input \+ output; never a sum of chunks/);
  assert.match(details, /`gen_ai\.usage\.output_tokens\.reasoning`/);
  assert.match(details, /only positive counts, and only when ordinary token usage is present/);
  assert.match(captured, /Embedding callbacks emit `gen_ai\.usage\.input_tokens` and `gen_ai\.usage\.total_tokens`/);
  assert.match(captured, /either exported count may be zero, and this mapping does not derive a missing total/);
  assert.doesNotMatch(captured, /never a placeholder 0/);
});

test('Eino resource privacy does not cover environment-supplied metadata', () => {
  const provider = page.split('## 3. Create the tracer provider')[1]?.split('## 4. Register')[0];
  assert.ok(provider, 'Keep exporter resource guidance');
  assert.match(provider, /enables no host, process or OS detectors/);
  assert.match(provider, /attributes supplied through `OTEL_RESOURCE_ATTRIBUTES` are still exported/);
  assert.match(provider, /privacy switches do not filter resource attributes/);
  assert.doesNotMatch(provider, /no host name, user name or local path is exported/);
  assert.match(main, /Review OTEL_RESOURCE_ATTRIBUTES separately/);
  assert.doesNotMatch(main, /no host name, user name or local path is exported/);
  assert.match(readme, /Keep sensitive values out of metadata and `OTEL_RESOURCE_ATTRIBUTES`/);
});

test('Eino privacy switches leave metadata and output image boundaries explicit', () => {
  const privacy = page.split('## Privacy')[1]?.split('## Errors')[0];
  assert.ok(privacy, 'Keep the customer-facing privacy section');
  const images = privacy.split('\n').find(line => line.startsWith('| `FI_HIDE_INPUT_IMAGES`, `FI_BASE64_IMAGE_MAX_LENGTH` |'));
  assert.ok(images, 'Keep the input image settings');
  assert.match(images, /only to structured input-message image attributes/);
  assert.match(images, /base64 `data:image\/` URLs/);
  assert.match(images, /Output images are unaffected/);
  assert.match(privacy, /not general-purpose metadata sanitizers/);
  assert.match(privacy, /Session\/user IDs, span and component names, document IDs, tool definitions and stop sequences can still be exported/);
  assert.match(privacy, /`FI_HIDE_LLM_INVOCATION_PARAMETERS` drops only the `gen_ai\.request\.parameters` JSON attribute, not individual request attributes/);
  assert.match(page, /It does not scrub arbitrary custom attributes/);
});

test('Eino captured attributes retain callback-specific conditions', () => {
  const captured = page.split('## What is captured')[1]?.split('## Privacy')[0];
  assert.ok(captured, 'Keep the callback mapping reference');
  assert.match(captured, /`ChatTemplate`, `AgenticChatTemplate`/);
  assert.match(captured, /`gen_ai\.agent\.name` \| agent spans with a non-empty `RunInfo\.Name`/);
  assert.match(captured, /embedding callbacks with a non-empty first vector; this mapping omits the vectors themselves/);
  assert.match(captured, /retrieval, embedding and indexer outputs use dedicated attributes instead/);
  assert.doesNotMatch(captured, /every span whose input or output can be encoded/);
});
