#!/usr/bin/env node
// Docs grep gate for TH-8323: the OpenAI Assistants page must state the sunset
// date and must never contain samples that call the retired API.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const page = join(dirname(fileURLToPath(import.meta.url)), '..', 'src/pages/docs/integrations/traceai/openai_assistants.mdx')
const text = readFileSync(page, 'utf8')
const errors = []
if (!text.includes('26 August 2026')) errors.push('missing "26 August 2026"')
for (const bad of ['beta.threads', 'beta.assistants', 'threads.runs', '/v1/assistants', 'api.openai.com']) {
  if (text.includes(bad)) errors.push(`forbidden string present: ${bad}`)
}
if (errors.length) { console.error('FAIL openai_assistants.mdx:\n - ' + errors.join('\n - ')); process.exit(1) }
console.log('PASS openai_assistants.mdx grep gate')
