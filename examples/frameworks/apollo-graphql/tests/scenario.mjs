// Child process for the fixture tests: a real Apollo Server 4 over HTTP, tracing wired exactly
// like server.mjs, driven by real HTTP requests. Prints one JSON line with what the client saw.
//   node tests/scenario.mjs [tracing-first|apollo-first]
const order = process.argv[2] ?? "tracing-first";
let telemetry;
if (order === "apollo-first") {
  await import("@apollo/server"); // WRONG order on purpose: Apollo (and graphql) load before tracing
  telemetry = await import("../instrumentation.mjs");
} else {
  telemetry = await import("../instrumentation.mjs");
}
const { createServer } = await import("../app.mjs");
const { startStandaloneServer } = await import("@apollo/server/standalone");

const server = createServer();
const { url } = await startStandaloneServer(server, { listen: { port: 0 } });
const post = async (body) => (await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).json();

const { metrics } = await import("@opentelemetry/api");
const out = { meterProvider: metrics.getMeterProvider().constructor.name };
out.hello = await post({ query: "query Hello { hello }", operationName: "Hello" });
out.profile = await post({ query: "query Profile($id: ID!) { profile(id: $id) { id name email } }", operationName: "Profile", variables: { id: process.env.MARKER_VARIABLE ?? "var-1" } });
out.wide = await post({ query: "query Wide { wide { f01 f02 f03 f04 f05 f06 f07 f08 f09 f10 f11 f12 f13 f14 f15 f16 f17 f18 f19 f20 } }", operationName: "Wide" });
out.boom = await post({ query: "query Boom { boom }", operationName: "Boom" });
out.partial = await post({ query: "query Partial { partial { ok bad } }", operationName: "Partial" });
out.literal = await post({ query: `query Lit { profile(id: "${process.env.MARKER_LITERAL ?? "lit-1"}") { id } }`, operationName: "Lit" });
out.anonymous = await post({ query: "{ hello }" });

await telemetry.flushTelemetry(); // force flush, not a wait for the batch timer
await server.stop();
const t0 = Date.now();
await telemetry.shutdownTelemetry();
out.shutdownMs = Date.now() - t0;
console.log("RESULT " + JSON.stringify(out));
