// Run a small tool-calling flow against Helicone (or a local stand-in) and trace it in Future AGI.
// Environment: FI_API_KEY, FI_SECRET_KEY, FI_BASE_URL (self-hosted Future AGI), HELICONE_SURFACE
// (gateway | proxy), HELICONE_BASE_URL, HELICONE_API_KEY, OPENAI_API_KEY (proxy only),
// HELICONE_MODEL, FI_PROJECT_NAME, DEMO_MARKER, DEMO_SCENARIOS (comma list of: chat, tools, stream, error).
// The last stdout line is a JSON summary. Secrets are never printed.
import { setupTracing, makeClient, type Surface } from "./helicone-tracing.ts";

const surface = (process.env.HELICONE_SURFACE ?? "gateway") as Surface;
const project = process.env.FI_PROJECT_NAME ?? "helicone-demo-ts";
const model = process.env.HELICONE_MODEL ?? "openai/gpt-4o-mini";
const marker = process.env.DEMO_MARKER ?? "HELI-MARK-demo";
const scenarios = (process.env.DEMO_SCENARIOS ?? "chat,tools,stream,error").split(",");

const tracerProvider = setupTracing(project);
const client = makeClient(surface, {
  heliconeKey: process.env.HELICONE_API_KEY!,
  providerKey: process.env.OPENAI_API_KEY,
  baseURL: process.env.HELICONE_BASE_URL,
  maxRetries: 0,
});

// Helicone's own headers. Helicone reads these; Future AGI does not.
const heliconeHeaders = {
  "Helicone-Session-Id": process.env.HELICONE_SESSION_ID ?? "helicone-session-ts",
  "Helicone-Session-Path": "/demo",
  "Helicone-Session-Name": "weather-demo",
  "Helicone-User-Id": process.env.HELICONE_USER_ID ?? "helicone-user-ts",
  "Helicone-Property-Environment": "e2e",
};

const tools = [
  {
    type: "function" as const,
    function: {
      name: "get_weather",
      description: "Get the current weather for a city.",
      parameters: { type: "object", properties: { city: { type: "string" } }, required: ["city"] },
    },
  },
];

const summary: Record<string, unknown> = { surface, project, scenarios: {} };
const done = summary.scenarios as Record<string, unknown>;

if (scenarios.includes("chat")) {
  const r = await client.chat.completions.create(
    { model, messages: [{ role: "user", content: `Say hello. Include ${marker}.` }] },
    { headers: heliconeHeaders },
  );
  done.chat = Boolean(r.choices[0]?.message?.content);
}

if (scenarios.includes("tools")) {
  const messages: any[] = [{ role: "user", content: `What is the weather in Paris? Include ${marker}.` }];
  const first = await client.chat.completions.create(
    { model, messages, tools, tool_choice: "required" },
    { headers: heliconeHeaders },
  );
  const msg = first.choices[0].message;
  messages.push(msg);
  for (const call of msg.tool_calls ?? []) {
    messages.push({ role: "tool", tool_call_id: call.id, content: "21C and sunny" });
  }
  const final = await client.chat.completions.create({ model, messages, tools }, { headers: heliconeHeaders });
  done.tools = Boolean(final.choices[0]?.message?.content);
}

if (scenarios.includes("stream")) {
  const stream = await client.chat.completions.create(
    {
      model,
      stream: true,
      stream_options: { include_usage: true },
      messages: [{ role: "user", content: `Count from 1 to 3, then say ${marker}.` }],
    },
    { headers: heliconeHeaders },
  );
  let text = "";
  for await (const chunk of stream) text += chunk.choices[0]?.delta?.content ?? "";
  done.stream = text.length > 0;
}

if (scenarios.includes("error")) {
  try {
    await client.chat.completions.create({
      model: process.env.DEMO_ERROR_MODEL ?? "force-500",
      messages: [{ role: "user", content: `hello ${marker}` }],
    });
    done.error = "no-error";
  } catch (err: any) {
    done.error = err?.constructor?.name ?? "Error";
  }
}

await tracerProvider.forceFlush();
await tracerProvider.shutdown();
console.log(JSON.stringify(summary));
