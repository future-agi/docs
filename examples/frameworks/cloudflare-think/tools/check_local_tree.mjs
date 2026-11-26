#!/usr/bin/env node
// Asserts the Think span tree that `wrangler dev` recorded, before anything leaves the machine.
//
//   node tools/check_local_tree.mjs --explorer http://127.0.0.1:8787 --payloads off|on [--tool] [--error-type Error] [--root-conversation] [--dump rows.json]
//
// Exit 0 when the contract holds. Prints the per-turn summary (ids and counts, no contents).
import { writeFileSync } from "node:fs";
import { checkTree, readSpans } from "./explorer.mjs";

const argv = process.argv.slice(2);
const get = (k) => {
  const i = argv.indexOf(`--${k}`);
  return i >= 0 ? argv[i + 1] : undefined;
};
const rows = await readSpans(get("explorer"));
if (get("dump")) writeFileSync(get("dump"), JSON.stringify(rows)); // raw rows, for building test fixtures
const result = checkTree(rows, {
  payloads: get("payloads"),
  tool: argv.includes("--tool"),
  errorType: get("error-type"),
  rootConversation: argv.includes("--root-conversation"),
});
console.log(JSON.stringify({ spans: rows.length, ...result }, null, 1));
process.exit(result.ok ? 0 : 1);
