// Send one message to a running eve server and wait for the turn to settle.
//   node scripts/invoke.mjs --url http://127.0.0.1:2000 "What's the weather in Paris?"
// Prints one JSON line: { sessionId, traceId, status, text, events }.
// EVE_AUTHORIZATION, when set, is sent as the Authorization header (a built
// server started with `eve start` rejects anonymous callers).
const argv = process.argv.slice(2);
const urlIdx = argv.indexOf("--url");
const base = (urlIdx >= 0 ? argv.splice(urlIdx, 2)[1] : process.env.EVE_URL ?? "http://127.0.0.1:2000").replace(/\/+$/, "");
const message = argv.join(" ") || "What's the weather in Paris?";
const timeoutMs = Number(process.env.INVOKE_TIMEOUT_MS ?? 120_000);

export async function invoke(baseUrl, text, { timeout = timeoutMs, authorization = process.env.EVE_AUTHORIZATION } = {}) {
  const signal = AbortSignal.timeout(timeout);
  const auth = authorization ? { authorization } : {};
  const created = await fetch(`${baseUrl}/eve/v1/session`, {
    method: "POST",
    headers: { "content-type": "application/json", ...auth },
    body: JSON.stringify({ message: text }),
    signal,
  });
  if (created.status !== 202 && !created.ok) throw new Error(`create session: HTTP ${created.status} ${await created.text()}`);
  const { sessionId } = await created.json();
  const res = await fetch(`${baseUrl}/eve/v1/session/${sessionId}/stream`, { headers: auth, signal });
  if (!res.ok) throw new Error(`stream: HTTP ${res.status}`);
  const decoder = new TextDecoder();
  let buffered = "";
  let traceId = null;
  let status = "unknown";
  let reply = "";
  const events = [];
  outer: for await (const chunk of res.body) {
    buffered += decoder.decode(chunk, { stream: true });
    let nl;
    while ((nl = buffered.indexOf("\n")) >= 0) {
      const line = buffered.slice(0, nl).trim();
      buffered = buffered.slice(nl + 1);
      if (!line) continue;
      const ev = JSON.parse(line);
      events.push(ev.type);
      if (ev.data?.trace?.traceId && !traceId) traceId = ev.data.trace.traceId;
      if (ev.type === "message.completed" && ev.data?.finishReason !== "tool-calls") reply = ev.data?.text ?? ev.data?.message ?? reply;
      if (ev.type === "turn.failed" || ev.type === "step.failed") status = "failed";
      if (ev.type === "session.waiting" || ev.type === "session.failed" || ev.type === "session.completed") {
        if (status === "unknown") status = ev.type === "session.waiting" ? "completed" : "failed";
        break outer;
      }
    }
  }
  return { sessionId, traceId, status, text: reply, events };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const out = await invoke(base, message);
  console.log(JSON.stringify(out));
}
