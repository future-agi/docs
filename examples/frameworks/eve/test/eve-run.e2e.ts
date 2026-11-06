// Real eve, no keys: `eve dev` with this example's instrumentation files, a
// deterministic OpenAI-compatible mock model, and a loopback OTLP recorder.
// Run: npm run test:eve (about a minute; starts eve twice).
import assert from "node:assert/strict";
import { type ChildProcess, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { rmSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { after, before, describe, test } from "node:test";

import { invoke } from "../scripts/invoke.mjs";
import { startMockModel } from "../scripts/mock-model.mjs";
import { startRecorder } from "../scripts/recorder.mjs";

const EXAMPLE = fileURLToPath(new URL("..", import.meta.url));
type Rec = Awaited<ReturnType<typeof startRecorder>>;
type Mock = Awaited<ReturnType<typeof startMockModel>>;

function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const s = createServer();
    s.listen(0, "127.0.0.1", () => { const { port } = s.address() as { port: number }; s.close(() => resolve(port)); });
  });
}

async function startEve(env: Record<string, string>): Promise<{ proc: ChildProcess; url: string; log: string[] }> {
  rmSync(`${EXAMPLE}.eve`, { recursive: true, force: true });
  const port = await freePort();
  const log: string[] = [];
  const proc = spawn("./node_modules/.bin/eve", ["dev", "--no-ui", "--port", String(port), "--host", "127.0.0.1"], {
    cwd: EXAMPLE,
    env: { ...process.env, FI_CAPTURE_CONTENT: "", ...env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  proc.stdout?.on("data", (d) => log.push(String(d)));
  proc.stderr?.on("data", (d) => log.push(String(d)));
  const url = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 120; i++) {
    try { await fetch(url); return { proc, url, log }; } catch { await new Promise((r) => setTimeout(r, 500)); }
  }
  proc.kill("SIGKILL");
  throw new Error(`eve dev did not start:\n${log.join("")}`);
}

async function stopEve(proc: ChildProcess): Promise<void> {
  if (proc.exitCode !== null) return;
  const exited = new Promise((r) => proc.once("exit", r));
  proc.kill("SIGINT");
  const timer = setTimeout(() => proc.kill("SIGKILL"), 20_000);
  await exited;
  clearTimeout(timer);
}

const spansOf = (rec: Rec, traceId: string) => rec.requests.flatMap((r) => r.spans).filter((s) => s.traceId === traceId);

describe("eve dev + recipe + mock model", { timeout: 300_000 }, () => {
  let rec: Rec;
  let mock: Mock;
  const env = () => ({
    FI_BASE_URL: `http://127.0.0.1:${rec.port}`,
    FI_API_KEY: "hermetic-api-key",
    FI_SECRET_KEY: "hermetic-secret-key",
    FI_PROJECT_NAME: "eve-hermetic",
    MODEL_BASE_URL: `http://127.0.0.1:${mock.port}/v1`,
    MODEL_API_KEY: "mock-key",
    MODEL_ID: "mock-model",
  });
  before(async () => { rec = await startRecorder({ port: 0 }); mock = await startMockModel({ port: 0 }); });
  after(() => { rec.server.close(); mock.server.close(); });

  test("content off: one trace per turn, eve.agent only, tool error, no content on the wire", async () => {
    const marker = `HERMOFF${randomBytes(4).toString("hex")}`;
    const eve = await startEve(env());
    let ok, bad;
    try {
      ok = await invoke(eve.url, `Use get_weather for the city "Paris ${marker}".`);
      bad = await invoke(eve.url, `Use get_weather for the city "Atlantis ${marker}".`);
    } finally {
      await stopEve(eve.proc);
    }
    assert.equal(ok.status, "completed", eve.log.join(""));
    assert.match(ok.text, new RegExp(marker), "the agent itself saw the marker");

    const all = rec.requests.flatMap((r) => r.spans);
    assert.deepEqual([...new Set(all.map((s) => s.scope.name))], ["eve.agent"], "workflow spans are dropped");
    for (const r of rec.requests) {
      assert.equal(r.body.includes(Buffer.from(marker)), false, "marker must not be exported");
      assert.equal(r.rawHeaders["x-api-key"], "hermetic-api-key");
      assert.equal(r.rawHeaders["x-secret-key"], "hermetic-secret-key");
    }

    const t = spansOf(rec, ok.traceId);
    const root = t.find((s) => s.name.startsWith("invoke_agent "));
    const steps = t.filter((s) => s.name === "agent.step");
    const chats = t.filter((s) => s.name === "chat mock-model");
    const tool = t.find((s) => s.name === "execute_tool get_weather");
    assert.ok(root && !root.parentSpanId, "invoke_agent is the trace root");
    assert.equal(root.resource.project_name, "eve-hermetic");
    assert.equal(steps.length, 2);
    assert.ok(steps.every((s) => s.parentSpanId === root.spanId));
    assert.equal(chats.length, 2);
    assert.ok([...chats, tool].every((s) => steps.some((p) => p.spanId === s?.parentSpanId)));
    assert.deepEqual(chats.map((c) => [c.attributes["gen_ai.usage.input_tokens"], c.attributes["gen_ai.usage.output_tokens"]]), [[11, 7], [23, 9]]);
    assert.equal(chats[0].attributes["gen_ai.request.model"], "mock-model");
    assert.equal(root.attributes["gen_ai.usage.input_tokens"], 34);

    const te = spansOf(rec, bad.traceId).find((s) => s.name === "execute_tool get_weather");
    assert.equal(te?.status.code, 2, "failing tool is ERROR");
    assert.equal(te?.status.message, "");
    assert.ok(te?.events.every((e: { name: string }) => e.name !== "exception"));
    assert.ok(spansOf(rec, bad.traceId).some((s) => s.name.startsWith("invoke_agent ")), "last turn before SIGINT was exported");
  });

  test("FI_CAPTURE_CONTENT=1: prompt, tool arguments and output are exported", async () => {
    rec.requests.length = 0;
    const marker = `HERMON${randomBytes(4).toString("hex")}`;
    const eve = await startEve({ ...env(), FI_CAPTURE_CONTENT: "1" });
    let ok;
    try {
      ok = await invoke(eve.url, `Use get_weather for the city "Rome ${marker}".`);
    } finally {
      await stopEve(eve.proc);
    }
    const t = spansOf(rec, ok.traceId);
    const chat = t.find((s) => s.name === "chat mock-model");
    const tool = t.find((s) => s.name === "execute_tool get_weather");
    assert.match(String(chat?.attributes["gen_ai.input.messages"]), new RegExp(marker));
    assert.match(String(tool?.attributes["gen_ai.tool.call.arguments"]), new RegExp(marker));
    assert.match(String(tool?.attributes["gen_ai.tool.call.result"]), new RegExp(marker));
  });
});
