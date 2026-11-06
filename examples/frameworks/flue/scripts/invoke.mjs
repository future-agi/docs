// Sends one message to a running Flue server (the built dist/server.mjs or
// `vite dev`) and waits for the submission to settle.
//   node scripts/invoke.mjs --url http://127.0.0.1:3000 --agent weather 'Use get_weather for the city "Paris".'
import { randomBytes } from "node:crypto";

export async function invoke(baseUrl, message, { agent = "weather", id = `inv-${randomBytes(4).toString("hex")}`, timeoutMs = 180_000 } = {}) {
  const url = `${baseUrl.replace(/\/+$/, "")}/agents/${agent}/${id}`;
  const post = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kind: "user", body: message }),
  });
  if (post.status !== 202) throw new Error(`POST ${url} -> ${post.status} ${await post.text()}`);
  const { submissionId } = await post.json();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 500));
    const history = await (await fetch(`${url}?view=history`)).json();
    const final = (history.messages ?? [])
      .filter((m) => m.role === "assistant" && m.submissionId === submissionId)
      .flatMap((m) => m.parts)
      .filter((p) => p.type === "text" && p.state === "done");
    if (final.length > 0) return { submissionId, id, text: final.map((p) => p.text).join("") };
  }
  throw new Error(`submission ${submissionId} did not settle within ${timeoutMs} ms`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
  const message = process.argv.at(-1);
  const out = await invoke(arg("url", "http://127.0.0.1:3000"), message, { agent: arg("agent", "weather") });
  console.log(JSON.stringify(out));
}
