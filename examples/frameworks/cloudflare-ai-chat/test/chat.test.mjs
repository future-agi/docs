import { test } from "node:test";
import assert from "node:assert/strict";
import { agentUrl, chatRequest } from "../tools/chat.mjs";

test("chat request is the frame useAgentChat sends", () => {
  const f = chatRequest("req-1", "hello");
  assert.equal(f.type, "cf_agent_use_chat_request");
  assert.equal(f.id, "req-1");
  assert.equal(f.init.method, "POST");
  const body = JSON.parse(f.init.body);
  assert.equal(body.trigger, "submit-message");
  assert.deepEqual(body.messages[0].parts, [{ type: "text", text: "hello" }]);
  assert.equal(body.messages[0].role, "user");
});

test("agent URL: kebab-case class name, encoded instance name, ws scheme", () => {
  assert.equal(agentUrl("http://127.0.0.1:8787", "a@b.com"), "ws://127.0.0.1:8787/agents/support-chat/a%40b.com");
  assert.equal(agentUrl("https://x.example/", "c1"), "wss://x.example/agents/support-chat/c1");
});
