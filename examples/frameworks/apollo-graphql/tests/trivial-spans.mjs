// Child process: counts field resolve spans for a query over default-resolved scalar fields.
//   node tests/trivial-spans.mjs <depth|ignoreTrivial|none>
import { NodeSDK, tracing } from "@opentelemetry/sdk-node";
import { GraphQLInstrumentation } from "@opentelemetry/instrumentation-graphql";
const mode = process.argv[2];
const config = { allowValues: false, ...(mode === "depth" ? { depth: 1 } : {}), ...(mode === "ignoreTrivial" ? { ignoreTrivialResolveSpans: true } : {}) };
const memory = new tracing.InMemorySpanExporter();
const processor = new tracing.SimpleSpanProcessor(memory);
const sdk = new NodeSDK({ resourceDetectors: [], spanProcessors: [processor], metricReaders: [], logRecordProcessors: [], instrumentations: [new GraphQLInstrumentation(config)] });
sdk.start();
const { createServer } = await import("../app.mjs");
const server = createServer();
await server.start();
await server.executeOperation({ query: "query Wide { wide { f01 f02 f03 f04 f05 f06 f07 f08 f09 f10 f11 f12 f13 f14 f15 f16 f17 f18 f19 f20 } }" });
await processor.forceFlush();
const names = memory.getFinishedSpans().map((s) => s.name);
console.log("RESULT " + JSON.stringify({ resolveSpans: names.filter((n) => n.startsWith("graphql.resolve")).length, total: names.length }));
await server.stop();
await sdk.shutdown();
