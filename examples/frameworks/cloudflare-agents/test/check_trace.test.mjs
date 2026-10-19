// tools/check_trace.py on small stored-span lists: the model-error shape a deployed Worker produces (the real
// Cloudflare export also marks the runtime's POST / fetch spans ERROR, without a message). Needs python3.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PY = process.env.PYTHON || "python3";
const havePy = spawnSync(PY, ["--version"], { stdio: "ignore" }).status === 0;
const TOOL = new URL("../tools/check_trace.py", import.meta.url).pathname;

const span = (id, parent, name, type, extra = {}) => ({
  id, trace_id: "t1", parent_span_id: parent, name, observation_type: type, status: "UNSET", status_message: "",
  model: null, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, attrs_string: {}, session: "s1", ...extra,
});

function modelError(runtimeMessage) {
  const err = (m) => ({ status: "ERROR", status_message: m });
  return [
    span("a", "", "POST", "chain", err(runtimeMessage)),
    span("b", "a", "fetch", "chain", { ...err(runtimeMessage), session: null }),
    span("c", "b", "POST", "chain", { ...err(runtimeMessage), session: null }),
    span("d", "c", "invoke_agent weather-agent", "agent", { ...err("AI_APICallError"), attrs_string: { "gen_ai.agent.name": "weather-agent" } }),
    span("e", "d", "chat bad-model", "llm", { ...err("AI_APICallError"), model: "bad-model" }),
    span("f", "e", "fetch", "chain", { ...err(runtimeMessage), session: null }),
  ];
}

function run(spans) {
  const dir = mkdtempSync(join(tmpdir(), "cfa-check-"));
  try {
    writeFileSync(join(dir, "spans.json"), JSON.stringify(spans));
    return spawnSync(PY, ["-I", TOOL, join(dir, "spans.json"), "model-error", "--model", "bad-model"], { encoding: "utf8" });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("check_trace model-error: runtime POST / fetch spans may be ERROR without a message", { skip: !havePy && "python3 not found" }, () => {
  const r = run(modelError(""));
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /^OK model-error/m);
});

test("check_trace model-error: a runtime span carrying error text fails", { skip: !havePy && "python3 not found" }, () => {
  const r = run(modelError("upstream said: no such model"));
  assert.equal(r.status, 1);
  assert.match(r.stdout, /runtime ERROR spans carry a message/);
});
