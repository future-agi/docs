// Audit public package references, not signed-in application routes.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const page = await readFile(new URL('../src/pages/docs/integrations/traceai/auto.mdx', import.meta.url), 'utf8');
const urls = new Set([...page.matchAll(/\]\((https:\/\/github\.com\/[^)]+)\)/g)].map(match => match[1]));
const documents = new Map();
for (const href of urls) {
  const url = new URL(href);
  const anchor = url.hash.slice(1);
  url.hash = '';
  const source = url.href.replace('https://github.com/future-agi/traceAI/blob/', 'https://raw.githubusercontent.com/future-agi/traceAI/');
  if (!documents.has(source)) {
    const response = await fetch(source, { signal: AbortSignal.timeout(30000) });
    assert.ok(response.ok, `${source}: ${response.status}`);
    documents.set(source, await response.text());
  }
  if (anchor && source.startsWith('https://raw.githubusercontent.com/')) {
    const headings = [...documents.get(source).matchAll(/^#{1,6} (.+)$/gm)].map(match => match[1].toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/ /g, '-'));
    assert.ok(headings.includes(anchor), `${href}: missing heading`);
  }
  console.log(`OK ${href}`);
}
console.log(JSON.stringify({ externalLinks: urls.size, fetchedDocuments: documents.size }));
