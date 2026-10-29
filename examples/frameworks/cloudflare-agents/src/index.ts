// A Cloudflare Agents SDK agent (npm `agents`, class `Agent`) whose turns are traced by Workers tracing.
//
// Nothing in this file talks to Future AGI. The Worker only creates spans; Cloudflare exports them to the
// OTLP destination named in wrangler.jsonc, and your collector (otelcol.yaml) forwards them to Future AGI.
//
//   Agent (agent_start, agent_initialization, ... spans)            emitted by `agents` itself
//   wrapAISDK(ai) (invoke_agent, chat, execute_tool, tool_approval)  emitted by agents/observability/ai
//
// A plain Agent does not trace model or tool calls on its own: without wrapAISDK you get the lifecycle spans
// only, with no model, token or tool spans.
import { tracing } from "cloudflare:workers";
import { Agent, routeAgentRequest } from "agents";
import { wrapAISDK } from "agents/observability/ai";
import { createOpenAI } from "@ai-sdk/openai";
import * as ai from "ai";
import { z } from "zod";

type Env = {
  WeatherAgent: DurableObjectNamespace;
  OPENAI_API_KEY: string; // secret: `wrangler secret put OPENAI_API_KEY`
  OPENAI_BASE_URL?: string; // optional, any OpenAI-compatible endpoint
  MODEL?: string;
  // Cloudflare's payload switches, both off unless set to "true". Off: no message text, tool arguments or
  // tool results are written to spans at all, so nothing of it leaves Cloudflare.
  STORE_MESSAGES?: string;
  STORE_TOOLS?: string;
};

// One instance (Durable Object) per conversation: POST /agents/weather-agent/<conversation> {"question": "..."}
export class WeatherAgent extends Agent<Env> {
  async onRequest(request: Request): Promise<Response> {
    if (request.method !== "POST") return new Response("POST {\"question\": \"...\"}", { status: 405 });
    const { question } = (await request.json()) as { question?: string };
    if (!question) return new Response("question is required", { status: 400 });

    const { generateText } = wrapAISDK(ai, {
      storeMessages: this.env.STORE_MESSAGES === "true",
      storeTools: this.env.STORE_TOOLS === "true",
    });
    const openai = createOpenAI({ apiKey: this.env.OPENAI_API_KEY, baseURL: this.env.OPENAI_BASE_URL });

    try {
      // Awaited inside the request: the invocation stays open until the turn ends, so every span closes
      // with its attributes before Cloudflare exports it. Background turns need this.ctx.waitUntil(...).
      const result = await generateText({
        model: openai.chat(this.env.MODEL ?? "gpt-4o-mini"),
        system: "You answer weather questions. Call get_weather once, then answer in one sentence.",
        prompt: question,
        tools: {
          get_weather: ai.tool({
            description: "Current weather for a city",
            inputSchema: z.object({ city: z.string() }),
            execute: async ({ city }) => {
              // Demo failure path: the tool throws, the turn continues, and execute_tool carries error.type.
              if (city.toLowerCase().includes("atlantis")) throw new Error(`no weather station for ${city}`);
              return { city, forecast: "sunny", celsius: 21 };
            },
          }),
        },
        // A server-side approval policy (no human in the loop). Cloudflare records it as a tool_approval span.
        toolApproval: { get_weather: "approved" },
        stopWhen: ai.isStepCount(3),
        // Agent identity on invoke_agent, chat and execute_tool (gen_ai.agent.name / .id, gen_ai.conversation.id).
        // The Durable Object id is the conversation: the Agent's own spans carry the same id, so one session.
        runtimeContext: { agentId: this.name, conversationId: this.ctx.id.toString() },
        telemetry: { functionId: "weather-agent", includeRuntimeContext: { agentId: true, conversationId: true } },
      });
      return Response.json({ answer: result.text, steps: result.steps.length });
    } catch (error) {
      // The spans already carry error.type (the error class). Do not echo provider error text to the caller.
      return Response.json({ error: (error as Error)?.name ?? "Error" }, { status: 502 });
    }
  }
}

export default {
  async fetch(request: Request, env: Env) {
    const response = await routeAgentRequest(request, env, {
      // Optional, recommended: put the conversation on the Worker's request span (the root of the trace), so
      // Future AGI lists the whole trace under the conversation's session. Same value the Agent's spans carry.
      onBeforeRequest: (_request, { name }) => {
        tracing.getActiveSpan()?.setAttribute("gen_ai.conversation.id", env.WeatherAgent.idFromName(name).toString());
      },
    });
    return response ?? new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
