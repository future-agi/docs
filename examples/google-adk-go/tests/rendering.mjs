// Engineering fixture: run the real product span-details data functions.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = resolve(process.argv[2]);
const frontend = resolve(process.argv[3]);
const sourcePath = resolve(frontend, 'src/components/traceDetailDrawer/DrawerRightRenderer/getSpanData.js');
const dependencyPath = resolve(frontend, 'src/components/traceDetailDrawer/DrawerRightRenderer/flattenedMessageAttrs.js');
const source = readFileSync(sourcePath, 'utf8');
// Resolve the original extensionless relative import for Node, with no logic changes.
const moduleSource = source.replace('"./flattenedMessageAttrs"', JSON.stringify(pathToFileURL(dependencyPath).href));
const { getLlmData } = await import(`data:text/javascript;base64,${Buffer.from(moduleSource).toString('base64')}`);
const captured = JSON.parse(readFileSync(resolve(root, 'evidence/v2-normal-SPAN_ONLY.json'), 'utf8'));
const model = captured.raw.filter(s => s.attrs['gen_ai.operation.name'] === 'generate_content');
assert.ok(model.length === 2 && model.every(s => s.attrs['gen_ai.input.messages']));
const checks = model.map(s => {
  const input = getLlmData({ span_attributes: s.attrs }, 'input');
  const output = getLlmData({ span_attributes: s.attrs }, 'output');
  return { nativeMessageContentPresent: true, displayedInputMessages: input.inputMessage.length, displayedOutputMessages: output.outputMessage.length, input: input.input, output: output.output };
});
const canRender = checks.every(c => c.displayedInputMessages > 0 && c.displayedOutputMessages > 0);
const result = {
  status: canRender ? 'CONTENT_RENDERING_AVAILABLE' : 'CONTENT_RENDERING_BLOCKED',
  reason: canRender
    ? 'Native message attributes populate the product message data. Review content privacy before adding an opt-in guide.'
    : 'Native ADK v2 message JSON does not populate every prompt/response card. Do not claim content support based on the native capture flag alone.',
  sourcePath,
  sourceSha256: createHash('sha256').update(source).digest('hex'),
  checks,
  customerRoute: 'Metadata-only; no message/tool rendering or parity claim is published.'
};
writeFileSync(resolve(root, 'evidence/rendering.json'), JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
