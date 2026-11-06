// The order of these two imports is the mechanism: tracing first, Apollo second.
import { shutdownTelemetry } from "./instrumentation.mjs";
import { createServer } from "./app.mjs";
import { startStandaloneServer } from "@apollo/server/standalone";

const server = createServer();
const { url } = await startStandaloneServer(server, { listen: { port: Number(process.env.PORT ?? 4000) } });
console.log(`Apollo Server 4 ready at ${url}`);

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, async () => {
    await server.stop();
    await shutdownTelemetry(); // flushes the last batch
    process.exit(0);
  });
}
