#!/usr/bin/env node
// Send one user message to the AIChatAgent over its WebSocket chat protocol (what useAgentChat does).
//
//   node tools/chat.mjs http://127.0.0.1:8787 <agent-instance-name> "<message>"
//
// Prints one JSON line with the outcome and the response length; never the response text.
// Exit 0 when the turn finished without a stream error.
export function chatRequest(id, text) {
  const message = { id: `m-${id}`, role: "user", parts: [{ type: "text", text }] };
  return {
    type: "cf_agent_use_chat_request",
    id,
    init: { method: "POST", body: JSON.stringify({ messages: [message], trigger: "submit-message" }) },
  };
}

export function agentUrl(base, instance, agent = "support-chat") {
  return base.replace(/^http/, "ws").replace(/\/+$/, "") + `/agents/${agent}/${encodeURIComponent(instance)}`;
}

async function main() {
  const [base, instance, text] = process.argv.slice(2);
  const ws = new WebSocket(agentUrl(base, instance));
  const id = "req-" + Math.random().toString(36).slice(2, 10);
  const seen = { done: false, error: false, chars: 0, tool_calls: 0, tool_errors: 0 };
  const timer = setTimeout(() => {
    console.log(JSON.stringify({ ...seen, timeout: true }));
    process.exit(2);
  }, 120_000);
  ws.addEventListener("open", () => ws.send(JSON.stringify(chatRequest(id, text))));
  ws.addEventListener("message", (ev) => {
    let d;
    try { d = JSON.parse(ev.data); } catch { return; }
    if (d.type !== "cf_agent_use_chat_response" || d.id !== id) return;
    if (d.error) seen.error = true;
    if (d.body?.trim()) {
      try {
        const c = JSON.parse(d.body);
        if (c.type === "text-delta") seen.chars += (c.delta ?? "").length;
        if (c.type === "tool-input-available") seen.tool_calls += 1;
        if (c.type === "tool-output-error") seen.tool_errors += 1;
      } catch {}
    }
    if (d.done) {
      seen.done = true;
      clearTimeout(timer);
      ws.close();
    }
  });
  ws.addEventListener("close", () => {
    console.log(JSON.stringify(seen));
    process.exit(seen.done && !seen.error ? 0 : 1);
  });
}

if (import.meta.url === `file://${process.argv[1]}`) main();
