const { CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN } = process.env;
if (!CLOUDFLARE_ACCOUNT_ID || !CLOUDFLARE_API_TOKEN) {
  throw new Error("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN.");
}

const response = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${CLOUDFLARE_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "@cf/meta/llama-3.2-1b-instruct",
      messages: [{ role: "user", content: "Say hello in one word." }],
      max_tokens: 16,
      stream: false,
    }),
    signal: AbortSignal.timeout(30_000),
  },
);
const result = await response.json();
if (!response.ok) {
  console.error(`Workers AI request failed (HTTP ${response.status}).`);
  process.exitCode = 1;
} else {
  console.log(result.choices[0].message.content);
}
