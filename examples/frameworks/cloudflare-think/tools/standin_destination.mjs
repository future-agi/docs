#!/usr/bin/env node
// STANDIN for Cloudflare's Workers Observability OTLP destination. Test tooling, not part of the recipe.
//
// In production, Cloudflare exports the Worker's traces to the destination you create in the dashboard,
// as OTLP/HTTP (JSON: Cloudflare does not support binary protobuf) with the custom headers you set.
// `wrangler dev` has no destinations, so this script reads the real spans that Think emitted from the
// Local Explorer and posts them the same way: OTLP/HTTP JSON, uncompressed, `Authorization: Bearer`.
//
//   node tools/standin_destination.mjs --explorer http://127.0.0.1:8787 \
//        --endpoint http://127.0.0.1:4318/v1/traces [--token-env COLLECTOR_TOKEN] [--out wire.json]
//
// Prints counts and HTTP statuses only, never span contents or the token.
import { writeFileSync } from "node:fs";
import { batches, readSpans, toOtlpJson } from "./explorer.mjs";

function args(argv) {
  const a = { tokenEnv: "COLLECTOR_TOKEN", max: 500 };
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i].replace(/^--/, "");
    a[k === "token-env" ? "tokenEnv" : k] = argv[i + 1];
  }
  if (!a.explorer || !a.endpoint) throw new Error("usage: --explorer <wrangler dev origin> --endpoint <collector /v1/traces URL>");
  return a;
}

export async function forward({ explorer, endpoint, token, max = 500, out }, fetchImpl = fetch) {
  const rows = await readSpans(explorer, fetchImpl);
  const bodies = batches(rows, Number(max)).map(toOtlpJson);
  const statuses = [];
  for (const body of bodies) {
    const headers = { "content-type": "application/json" };
    if (token) headers.authorization = `Bearer ${token}`;
    const res = await fetchImpl(endpoint, { method: "POST", headers, body: JSON.stringify(body) });
    statuses.push(res.status);
  }
  if (out) writeFileSync(out, JSON.stringify(bodies));
  const traceIds = [...new Set(rows.map((r) => r.trace_id))];
  return { spans: rows.length, traces: traceIds.length, requests: bodies.length, statuses, trace_ids: traceIds };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = args(process.argv.slice(2));
  const result = await forward({ ...a, token: process.env[a.tokenEnv] });
  console.log(JSON.stringify(result));
  process.exit(result.statuses.every((s) => s >= 200 && s < 300) ? 0 : 1);
}
