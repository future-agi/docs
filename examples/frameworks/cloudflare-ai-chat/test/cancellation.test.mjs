// Exercise the shipped Worker and the real AIChatAgent cancellation protocol in workerd.
// The provider is loopback-only; Wrangler gets a disposable home and synthetic credentials.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { agentUrl, chatRequest } from "../tools/chat.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const listen = (server) => new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", () => resolve(server.address().port));
});
async function unusedPort() {
  const server = createServer();
  const port = await listen(server);
  await new Promise((resolve) => server.close(resolve));
  return port;
}

test("cancelling useAgentChat aborts the provider request before it finishes", { timeout: 60_000 }, async (t) => {
  const home = mkdtempSync(join(root, ".cancel-test-"));
  let worker;
  let ws;
  t.after(async () => {
    ws?.close();
    if (worker && worker.exitCode === null && worker.signalCode === null) {
      const exited = once(worker, "exit");
      worker.kill("SIGTERM");
      const timer = setTimeout(() => worker.kill("SIGKILL"), 5_000);
      try { await exited; } finally { clearTimeout(timer); }
    }
    rmSync(home, { recursive: true, force: true });
  });
  let providerStarted = false;
  let providerFinished = false;
  let providerClosed = false;
  const provider = createServer(async (request, response) => {
    // Drain the request so close below describes the response, not the request body.
    for await (const _ of request) { /* consume */ }
    providerStarted = true;
    response.on("close", () => { providerClosed = true; });
    response.writeHead(200, { "content-type": "text/event-stream" });
    const send = (delta, finish_reason = null) => response.write(`data: ${JSON.stringify({
      id: "synthetic-cancellation", object: "chat.completion.chunk", created: 1,
      model: "gpt-4o-mini", choices: [{ index: 0, delta, finish_reason }],
    })}\n\n`);
    send({ role: "assistant" });
    send({ content: "Starting response." });
    for (let i = 0; i < 30 && !response.destroyed; i++) {
      await delay(100);
      if (!response.destroyed) send({ content: " Still generating." });
    }
    if (!response.destroyed) {
      providerFinished = true;
      send({}, "stop");
      response.end("data: [DONE]\n\n");
    }
  });
  t.after(() => { provider.closeAllConnections(); provider.close(); });
  const modelPort = await listen(provider);
  const port = await unusedPort();
  const inspectorPort = await unusedPort();
  let output = "";
  worker = spawn(process.execPath, [
    join(root, "node_modules/wrangler/bin/wrangler.js"), "dev", "--local",
    "--config", join(root, "wrangler.jsonc"), "--persist-to", join(home, "state"),
    "--port", String(port), "--inspector-port", String(inspectorPort), "--ip", "127.0.0.1",
    "--var", "OPENAI_API_KEY:synthetic-not-a-key",
    "--var", `OPENAI_BASE_URL:http://127.0.0.1:${modelPort}/v1`,
    "--var", "MODEL:gpt-4o-mini", "--log-level", "warn",
  ], {
    cwd: root,
    env: { PATH: process.env.PATH, HOME: home, WRANGLER_SEND_METRICS: "false", CI: "true" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  worker.stdout.on("data", (chunk) => { output += chunk; });
  worker.stderr.on("data", (chunk) => { output += chunk; });
  let ready = false;
  for (let i = 0; i < 80; i++) {
    assert.equal(worker.exitCode, null, `Wrangler exited: ${output}`);
    try { await fetch(`http://127.0.0.1:${port}/`); ready = true; break; } catch { /* starting */ }
    await delay(500);
  }
  assert.ok(ready, `Wrangler did not start: ${output}`);

  ws = new WebSocket(agentUrl(`http://127.0.0.1:${port}`, "cancellation-regression"));
  const id = "cancel-request";
  let cancelled = false;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Client did not receive a terminal frame")), 10_000);
    const fail = (error) => { clearTimeout(timer); reject(error); };
    ws.addEventListener("error", () => fail(new Error("WebSocket error")));
    ws.addEventListener("open", () => ws.send(JSON.stringify(chatRequest(id, "Write a long response."))));
    ws.addEventListener("message", ({ data }) => {
      const frame = JSON.parse(data);
      if (frame.id !== id || frame.type !== "cf_agent_use_chat_response") return;
      if (frame.error) return fail(new Error(`Chat stream error: ${frame.body}`));
      if (!cancelled && frame.body?.includes("text-delta")) {
        cancelled = true;
        ws.send(JSON.stringify({ id, type: "cf_agent_chat_request_cancel" }));
      }
      if (frame.done) { clearTimeout(timer); resolve(); }
    });
  });
  // Keep the socket open: the cancellation frame alone must stop the provider.
  for (let i = 0; i < 50 && !providerClosed; i++) await delay(100);
  assert.ok(providerStarted, "the real Worker must call the loopback provider");
  assert.ok(cancelled, "the client must cancel after receiving model output");
  assert.ok(providerClosed, "the provider connection must close after cancellation");
  assert.equal(providerFinished, false, "the provider must abort, not finish generating after the client turn ends");
});
