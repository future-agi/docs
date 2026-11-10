#!/usr/bin/env node
/** Generate a bounded Skills-only Swagger subset; run on the cloud docs lane. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [source, revision] = process.argv.slice(2);
if (!source || !/^[a-f0-9]{40}$/.test(revision ?? '')) {
  throw new Error('Usage: node scripts/generate-skills-reference.mjs SWAGGER_JSON PRODUCT_SHA');
}
const raw = fs.readFileSync(source);
const contract = JSON.parse(raw);
const paths = Object.fromEntries(Object.entries(contract.paths)
  .filter(([route]) => route.startsWith('/model-hub/skills/')));
const definitions = {};
function collect(value) {
  if (!value || typeof value !== 'object') return;
  if (typeof value.$ref === 'string') {
    const name = value.$ref.replace(/^#\/definitions\//, '');
    if (!Object.hasOwn(contract.definitions, name)) throw new Error(`Missing schema: ${name}`);
    if (!Object.hasOwn(definitions, name)) {
      definitions[name] = contract.definitions[name];
      collect(definitions[name]);
    }
  }
  for (const child of Object.values(value)) collect(child);
}
collect(paths);
const output = {
  provenance: {
    product_commit: revision,
    source: 'api_contracts/openapi/swagger.json',
    sha256: crypto.createHash('sha256').update(raw).digest('hex'),
    verification: 'schema-derived; live request/response examples are not verified by this generator',
  },
  swagger: contract.swagger,
  info: { title: 'Skills and agent contexts', version: revision },
  paths,
  definitions: Object.fromEntries(Object.entries(definitions).sort(([a], [b]) => a.localeCompare(b))),
};
fs.mkdirSync(path.join(root, 'public/api'), { recursive: true });
fs.writeFileSync(path.join(root, 'public/api/skills-sealed.json'), `${JSON.stringify(output, null, 2)}\n`);
const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'options']);
const operations = Object.values(paths).reduce((n, item) => n + Object.keys(item).filter(k => methods.has(k)).length, 0);
console.log(JSON.stringify({ paths: Object.keys(paths).length, operations, schemas: Object.keys(definitions).length, ...output.provenance }, null, 2));
