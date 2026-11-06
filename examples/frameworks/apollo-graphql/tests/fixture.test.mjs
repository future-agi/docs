// Fixture tests for the Apollo Server 4 recipe (TH-8279). Each scenario runs a real Apollo
// Server 4 over HTTP in a child process, exports with the real OTLP/HTTP exporter to a local
// collector, and asserts on what the collector received. No network, no Apollo cloud account,
// no model call. Acceptance IDs refer to the PRD (AC-01 .. AC-13).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { startCollector } from "./collector.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MARKER_VARIABLE = "MARKER-VAR-7f3a91";
const MARKER_LITERAL = "MARKER-LIT-5c2d08";
const MARKER_ERROR = "resolver failed"; // the thrown message in app.mjs

function runScenario(order, env = {}) {
  return new Promise(async (resolve, reject) => {
    const collector = await startCollector();
    const child = spawn(process.execPath, [path.join(root, "tests", "scenario.mjs"), order], {
      cwd: root,
      env: { ...process.env, FI_BASE_URL: collector.url, FI_API_KEY: "test-key", FI_SECRET_KEY: "test-secret", FI_PROJECT_NAME: "apollo-fixture", MARKER_VARIABLE, MARKER_LITERAL, ...env },
    });
    let stdout = "", stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("close", async (code) => {
      const line = stdout.split("\n").find((l) => l.startsWith("RESULT "));
      const result = line ? JSON.parse(line.slice(7)) : null;
      resolve({ code, result, stderr, collector });
    });
    child.on("error", reject);
  });
}

let run, runContent, runWrongOrder;
before(async () => {
  run = await runScenario("tracing-first");
  runContent = await runScenario("tracing-first", { FI_APOLLO_CAPTURE_CONTENT: "true" });
  runWrongOrder = await runScenario("apollo-first");
});
after(async () => {
  for (const r of [run, runContent, runWrongOrder]) await r?.collector.close();
});

const byOperation = (spans, name) => spans.filter((s) => s.attributes["graphql.operation.name"] === name && s.name.startsWith("query"));
const traceOf = (spans, traceId) => spans.filter((s) => s.traceId === traceId);

test("the scenario runs and answers every query", () => {
  assert.equal(run.code, 0, run.stderr);
  assert.equal(run.result.hello.data.hello, "world");
  assert.equal(run.result.profile.data.profile.name, "Ada");
  assert.ok(run.result.boom.errors?.length, "the throwing query returns a GraphQL error");
});

test("AC-01 server.mjs imports the instrumentation before Apollo", () => {
  const imports = [...readFileSync(path.join(root, "server.mjs"), "utf8").matchAll(/^import .*?from "(.+?)";/gm)].map((m) => m[1]);
  assert.equal(imports[0], "./instrumentation.mjs");
  assert.ok(imports.indexOf("./instrumentation.mjs") < imports.findIndex((i) => i.startsWith("@apollo/")));
  // app.mjs is the only module that imports @apollo/server, and server.mjs loads it second.
  assert.ok(imports.indexOf("./instrumentation.mjs") < imports.indexOf("./app.mjs"));
  assert.ok(!imports.includes("@apollo/server"), "server.mjs must not import @apollo/server before the tracing import");
});

test("AC-01 the order matters: Apollo loaded first produces no GraphQL spans", () => {
  const graphqlSpans = runWrongOrder.collector.spans().filter((s) => s.name.startsWith("graphql.") || s.name.startsWith("query "));
  assert.equal(graphqlSpans.length, 0, "wrong import order must leave graphql unpatched");
  assert.ok(runWrongOrder.result.hello.data, "the server still answers");
});

test("AC-02 the Apollo package is @apollo/server, pinned exactly in package.json and the lockfile", () => {
  const pin = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8")).dependencies["@apollo/server"];
  assert.match(pin, /^\d+\.\d+\.\d+$/, "exact pin, no range");
  const lock = JSON.parse(readFileSync(path.join(root, "package-lock.json"), "utf8"));
  assert.equal(lock.packages["node_modules/@apollo/server"].version, pin);
  const installed = JSON.parse(readFileSync(path.join(root, "node_modules/@apollo/server/package.json"), "utf8")).version;
  assert.equal(installed, pin);
  // The recipe is written and committed for Server 4; APOLLO_PIN_MAJOR lets the matrix leg run against another major.
  assert.equal(pin.split(".")[0], process.env.APOLLO_PIN_MAJOR ?? "4");
  assert.equal(lock.packages["node_modules/@opentelemetry/instrumentation-graphql"].version, "0.71.0");
});

test("AC-03 one operation is one trace: HTTP, execute and resolve spans share a trace id", () => {
  const spans = run.collector.spans();
  const op = byOperation(spans, "Hello")[0];
  assert.ok(op, "query Hello execute span exists");
  const trace = traceOf(spans, op.traceId);
  const names = trace.map((s) => s.name);
  assert.ok(names.includes("POST"), `HTTP server span in the same trace: ${names}`);
  assert.ok(names.includes("graphql.parse") && names.includes("graphql.validate"), `parse and validate in the same trace: ${names}`);
  assert.ok(names.includes("graphql.resolve hello"), names.join());
  const http = trace.find((s) => s.name === "POST");
  assert.ok(!http.parentSpanId, "HTTP span is the root");
  assert.equal(op.parentSpanId.length > 0, true, "execute span has a parent (the HTTP span)");
});

test("AC-04 a resolver sees the graphql.resolve span as active and its child shares the trace", () => {
  const spans = run.collector.spans();
  const op = byOperation(spans, "Profile")[0];
  const trace = traceOf(spans, op.traceId);
  const resolve = trace.find((s) => s.name === "graphql.resolve profile");
  const child = trace.find((s) => s.name === "load-profile");
  assert.ok(resolve && child);
  assert.equal(child.parentSpanId, resolve.spanId);
  assert.equal(child.attributes["example.parent.name"], "graphql.resolve profile");
});

test("AC-05 depth:1 bounds the field spans; ignoreTrivialResolveSpans is not claimed", () => {
  const spans = run.collector.spans();
  const op = byOperation(spans, "Wide")[0];
  const trace = traceOf(spans, op.traceId);
  const fieldSpans = trace.filter((s) => s.name.startsWith("graphql.resolve"));
  assert.equal(fieldSpans.length, 1, "20 scalar fields under wide: only the depth-1 field is spanned");
  assert.ok(trace.length <= 8, `whole trace stays small: ${trace.length}`);
});

test("AC-06 default export has no variable values, no literals, no query text, no error text", () => {
  const wire = JSON.stringify(run.collector.requests.map((r) => r.body));
  for (const needle of [MARKER_VARIABLE, MARKER_LITERAL, "graphql.source", "$id: ID!", "{ hello }", MARKER_ERROR, "exception.message", "exception.stacktrace", root]) {
    assert.ok(!wire.includes(needle), `default export must not contain ${needle}`);
  }
  // Operation names are kept, anonymous operations have none.
  assert.ok(byOperation(run.collector.spans(), "Hello").length === 1);
});

test("AC-06 opt-in keeps the masked query text and the error message, never the stack or the variable values", () => {
  const wire = JSON.stringify(runContent.collector.requests.map((r) => r.body));
  assert.ok(wire.includes("graphql.source"));
  assert.ok(wire.includes(MARKER_ERROR));
  assert.ok(!wire.includes("exception.stacktrace"));
  assert.ok(!wire.includes(MARKER_VARIABLE), "variable values are never exported");
  assert.ok(!wire.includes(MARKER_LITERAL), "allowValues:false masks inline literals even with the opt-in");
});

test("AC-07 the collector sees both auth headers, the right path, and the resource attributes", () => {
  const req = run.collector.requests[0];
  assert.equal(req.method, "POST");
  assert.equal(req.path, "/tracer/v1/traces");
  assert.equal(req.headers["x-api-key"], "test-key");
  assert.equal(req.headers["x-secret-key"], "test-secret");
  assert.ok(!req.headers["content-encoding"], "no gzip");
  const resource = run.collector.resourceAttributes();
  assert.equal(resource.project_name, "apollo-fixture");
  assert.equal(resource.project_type, "observe");
  for (const k of ["host.name", "host.arch", "process.command_args", "process.owner", "process.executable.path", "process.pid"]) {
    assert.ok(!(k in resource), `no ${k} resource attribute`);
  }
});

test("traces only: no metric or log exporter is started and shutdown does not stall", () => {
  assert.match(run.result.meterProvider, /Noop|Proxy/, run.result.meterProvider);
  assert.ok(run.result.shutdownMs < 2000, `shutdown took ${run.result.shutdownMs} ms`);
});

test("AC-08 a throwing resolver is ERROR on the resolve span and the operation span", () => {
  const spans = run.collector.spans();
  const op = byOperation(spans, "Boom")[0];
  const resolve = traceOf(spans, op.traceId).find((s) => s.name === "graphql.resolve boom");
  assert.equal(resolve.status.code, 2, "resolve span ERROR");
  assert.equal(resolve.events[0].name, "exception");
  assert.deepEqual(resolve.events[0].attributes.map((a) => a.key), ["exception.type"]);
  // The stock instrumentation leaves the execute span UNSET (observed on 4.13.0); the recipe's responseHook marks it.
  assert.equal(op.status?.code, 2, "operation span ERROR");
  assert.ok(!op.status?.message, "no error text on the status");
  const okOp = byOperation(spans, "Hello")[0];
  assert.ok((okOp.status?.code ?? 0) !== 2, "a successful operation is not ERROR");
});

test("AC-08 partial success: data plus errors marks the operation span ERROR", () => {
  const spans = run.collector.spans();
  const op = byOperation(spans, "Partial")[0];
  assert.ok(run.result.partial.data.partial.ok === "fine" && run.result.partial.errors.length === 1);
  const trace = traceOf(spans, op.traceId);
  // depth:1 means the nested failing field has no span of its own; the error shows on the operation span.
  assert.equal(op.status?.code, 2, "partial success: operation span ERROR");
  assert.ok(!trace.some((s) => s.name === "graphql.resolve partial.bad"));
  assert.equal(trace.find((s) => s.name === "graphql.resolve partial").status?.code ?? 0, 0);
});

test("AC-09 the scenario exports without sleeping for the batch interval", () => {
  // scenario.mjs calls flushTelemetry() and exits; the default batch delay is 5 s.
  assert.ok(run.collector.spans().length > 10);
  assert.match(readFileSync(path.join(root, "tests", "scenario.mjs"), "utf8"), /flushTelemetry\(\)/);
  assert.doesNotMatch(readFileSync(path.join(root, "tests", "scenario.mjs"), "utf8"), /setTimeout|\bsleep\b/);
});

test("AC-10 the example does not ship or claim a gateway", () => {
  const page = readFileSync(path.join(root, "README.md"), "utf8");
  assert.match(page, /gateway/i);
  assert.doesNotMatch(readFileSync(path.join(root, "package.json"), "utf8"), /@apollo\/gateway|@apollo\/subgraph/);
});

test("AC-11 no Gateway, Router or Studio dependency is installed", () => {
  const lock = JSON.parse(readFileSync(path.join(root, "package-lock.json"), "utf8"));
  const names = Object.keys(lock.packages);
  for (const bad of ["@apollo/gateway", "@apollo/federation", "@apollo/subgraph", "@apollo/rover", "@apollo/router"]) {
    assert.ok(!names.some((n) => n.endsWith(bad)), `${bad} must not be installed`);
  }
});

test("AC-12 a GraphQL-only trace has no LLM span", () => {
  for (const s of run.collector.spans()) {
    assert.ok(!("fi.span.kind" in s.attributes) || s.attributes["fi.span.kind"] !== "LLM");
    assert.ok(!Object.keys(s.attributes).some((k) => k.startsWith("llm.") || k.startsWith("gen_ai.")));
  }
});

test("AC-13 the base URL is {FI_BASE_URL}/tracer/v1/traces", () => {
  assert.match(readFileSync(path.join(root, "instrumentation.mjs"), "utf8"), /\$\{baseUrl\}\/tracer\/v1\/traces/);
  assert.ok(run.collector.requests.every((r) => r.path === "/tracer/v1/traces"));
});

test("lifecycle: SIGTERM flushes the last batch and a rejecting endpoint does not crash the server", async () => {
  const { spawn } = await import("node:child_process");
  const run = (baseUrl) => new Promise(async (resolve) => {
    const child = spawn(process.execPath, [path.join(root, "server.mjs")], { cwd: root, env: { ...process.env, FI_BASE_URL: baseUrl, FI_API_KEY: "k", FI_SECRET_KEY: "s", PORT: "0" } });
    let out = "", err = "";
    child.stdout.on("data", (d) => (out += d)); child.stderr.on("data", (d) => (err += d));
    const port = await new Promise((r) => { const t = setInterval(() => { const m = out.match(/ready at http:\/\/localhost:(\d+)/); if (m) { clearInterval(t); r(m[1]); } }, 50); });
    await fetch(`http://127.0.0.1:${port}/`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ query: "{ hello }" }) });
    child.kill("SIGTERM");
    child.on("close", (code, signal) => resolve({ code, signal, err }));
  });
  const collector = await startCollector();
  try {
    const ok = await run(collector.url);
    assert.equal(ok.code, 0, `exit code (signal ${ok.signal}): ${ok.err}`);
    assert.ok(collector.spans().some((s) => s.name.startsWith("query")), "the batch was exported on SIGTERM, not on the 5 s timer");
  } finally {
    await collector.close();
  }
  const refused = await run("http://127.0.0.1:1"); // nothing listens: export fails
  assert.equal(refused.code, 0, `server exits cleanly although the export failed: ${refused.err}`);
  assert.match(refused.err, /telemetry export failed/);
});
