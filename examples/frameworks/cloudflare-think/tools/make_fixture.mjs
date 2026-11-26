#!/usr/bin/env node
// Builds a test fixture from rows dumped by check_local_tree.mjs --dump: drops the Durable Object
// storage leaf spans (the collector drops them too) and replaces the run's marker with "MARKER".
//   node tools/make_fixture.mjs <rows.json> <marker> <out.json>
import { readFileSync, writeFileSync } from "node:fs";

const [src, marker, out] = process.argv.slice(2);
const rows = JSON.parse(readFileSync(src, "utf8")).filter((r) => !r.name.startsWith("durable_object_storage_"));
const text = JSON.stringify(rows, null, 1).split(marker).join("MARKER");
writeFileSync(out, text + "\n");
console.log(`${rows.length} spans -> ${out}`);
