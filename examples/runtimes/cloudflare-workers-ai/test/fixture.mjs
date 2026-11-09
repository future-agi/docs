// Test transport only. Loaded before the real traceAI preload; never calls Cloudflare.
import assert from "node:assert/strict";

const originalFetch = globalThis.fetch;
globalThis.fetch = async (url, options) => {
  if (new URL(url).hostname === "127.0.0.1") return originalFetch(url, options);
  assert.equal(url, "https://api.cloudflare.com/client/v4/accounts/test-account/ai/v1/chat/completions");
  assert.equal(options.method, "POST");
  assert.equal(options.headers.Authorization, "Bearer synthetic-cloudflare-token");
  assert.equal(options.headers["Content-Type"], "application/json");
  assert.ok(options.signal instanceof AbortSignal);
  assert.deepEqual(JSON.parse(options.body), {
    model: "@cf/meta/llama-3.2-1b-instruct",
    messages: [{ role: "user", content: "Say hello in one word." }],
    max_tokens: 16,
    stream: false,
  });
  const status = Number(process.env.TEST_HTTP_STATUS ?? 200);
  const body = status === 200
    ? {
      id: "fixture-completion",
      object: "chat.completion",
      model: "@cf/meta/llama-3.2-1b-instruct",
      choices: [{ index: 0, message: { role: "assistant", content: "Hello-fixture!" }, finish_reason: "stop" }],
      usage: { prompt_tokens: 12, completion_tokens: 4, total_tokens: 16 },
    }
    : { error: { message: "synthetic-cloudflare-token Say hello in one word.", type: "permission_error" } };
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
};
