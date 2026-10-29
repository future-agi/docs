// Deterministic OpenAI-compatible chat completions server for the hermetic
// eve test. First call: one get_weather tool call for the quoted city in the
// user message. After a tool result: a one-sentence answer. Streams (SSE) when
// asked to, reports usage, and answers 401 for the key "bad-key".
//   node scripts/mock-model.mjs --port 8399
import { createServer } from "node:http";

const USAGE = [
  { prompt_tokens: 11, completion_tokens: 7, total_tokens: 18 },
  { prompt_tokens: 23, completion_tokens: 9, total_tokens: 32 },
];

function textOf(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((p) => p?.text ?? "").join("");
  return "";
}

function plan(body) {
  const messages = body.messages ?? [];
  const toolMsg = [...messages].reverse().find((m) => m.role === "tool");
  if (toolMsg) {
    let result = {};
    try { result = JSON.parse(textOf(toolMsg.content)); } catch { /* error text */ }
    const text = result.city ? `${result.city} is ${String(result.condition).toLowerCase()} and ${result.temperatureF}°F.` : "The weather service failed.";
    return { kind: "text", text, usage: USAGE[1] };
  }
  const user = [...messages].reverse().find((m) => m.role === "user");
  const city = /city "([^"]+)"/.exec(textOf(user?.content))?.[1] ?? "Paris";
  return { kind: "tool", args: JSON.stringify({ city }), usage: USAGE[0] };
}

export function startMockModel({ port = 0 } = {}) {
  const calls = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    if (!req.url.endsWith("/chat/completions")) { res.writeHead(404).end(); return; }
    if (req.headers.authorization === "Bearer bad-key") {
      res.writeHead(401, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: { message: "Incorrect API key provided.", type: "invalid_request_error", code: "invalid_api_key" } }));
      return;
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const p = plan(body);
    calls.push({ stream: Boolean(body.stream), kind: p.kind, model: body.model });
    const id = `chatcmpl-mock-${calls.length}`;
    const base = { id, object: "chat.completion.chunk", created: 1_700_000_000, model: body.model };
    if (!body.stream) {
      const message = p.kind === "tool"
        ? { role: "assistant", content: null, tool_calls: [{ id: `call_mock_${calls.length}`, type: "function", function: { name: "get_weather", arguments: p.args } }] }
        : { role: "assistant", content: p.text };
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ ...base, object: "chat.completion", choices: [{ index: 0, message, finish_reason: p.kind === "tool" ? "tool_calls" : "stop" }], usage: p.usage }));
      return;
    }
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    const send = (o) => res.write(`data: ${JSON.stringify(o)}\n\n`);
    if (p.kind === "tool") {
      send({ ...base, choices: [{ index: 0, delta: { role: "assistant", tool_calls: [{ index: 0, id: `call_mock_${calls.length}`, type: "function", function: { name: "get_weather", arguments: p.args } }] }, finish_reason: null }] });
      send({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }] });
    } else {
      for (const piece of p.text.match(/.{1,12}/g)) send({ ...base, choices: [{ index: 0, delta: { role: "assistant", content: piece }, finish_reason: null }] });
      send({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "stop" }] });
    }
    send({ ...base, choices: [], usage: p.usage });
    res.end("data: [DONE]\n\n");
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({ server, port: server.address().port, calls })));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const i = process.argv.indexOf("--port");
  const { port } = await startMockModel({ port: i > 0 ? Number(process.argv[i + 1]) : 8399 });
  console.log(`mock model listening on http://127.0.0.1:${port}/v1`);
}
