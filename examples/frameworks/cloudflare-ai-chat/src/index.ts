// A Cloudflare AI Chat agent (@cloudflare/ai-chat) whose turns are traced by Workers tracing.
//
// Nothing in this file talks to Future AGI. The Worker only creates spans; Cloudflare exports them to the
// OTLP destination named in wrangler.jsonc, and your collector (otelcol.yaml) forwards them to Future AGI.
//
//   AIChatAgent (chat_turn, persist_*, ... spans)      emitted by @cloudflare/ai-chat itself
//   wrapAISDK(ai) (invoke_agent, chat, execute_tool)   emitted by agents/observability/ai
//
// Without wrapAISDK you still get the AIChatAgent spans, but no model, token or tool spans.
import { AIChatAgent } from "@cloudflare/ai-chat";
import { routeAgentRequest } from "agents";
import { wrapAISDK } from "agents/observability/ai";
import { createOpenAI } from "@ai-sdk/openai";
import * as ai from "ai";
import { z } from "zod";

type Env = {
  SupportChat: DurableObjectNamespace;
  OPENAI_API_KEY: string; // secret: `wrangler secret put OPENAI_API_KEY`
  OPENAI_BASE_URL?: string; // optional, any OpenAI-compatible endpoint
  MODEL?: string;
  // Cloudflare's payload switches, both off unless set to "true". Off: no message text, tool arguments or
  // tool results are written to spans at all, so nothing of it leaves Cloudflare.
  STORE_MESSAGES?: string;
  STORE_TOOLS?: string;
};

export class SupportChat extends AIChatAgent<Env> {
  async onChatMessage() {
    const { streamText } = wrapAISDK(ai, {
      storeMessages: this.env.STORE_MESSAGES === "true",
      storeTools: this.env.STORE_TOOLS === "true",
    });
    const openai = createOpenAI({ apiKey: this.env.OPENAI_API_KEY, baseURL: this.env.OPENAI_BASE_URL });

    const result = streamText({
      model: openai.chat(this.env.MODEL ?? "gpt-4o-mini"),
      system: "You are a support agent. Use the lookup_order tool for any order id.",
      messages: await ai.convertToModelMessages(this.messages),
      tools: {
        lookup_order: ai.tool({
          description: "Look up an order by id",
          inputSchema: z.object({ orderId: z.string() }),
          execute: async ({ orderId }) => {
            // Demo failure path: the tool throws, the turn continues, and the execute_tool span carries error.type.
            if (orderId.startsWith("FAIL")) throw new Error(`order backend unavailable for ${orderId}`);
            return { orderId, status: "shipped" };
          },
        }),
      },
      stopWhen: ai.isStepCount(3),
      // Agent identity on invoke_agent, chat and execute_tool (gen_ai.agent.name / .id, gen_ai.conversation.id).
      runtimeContext: { agentId: this.name, conversationId: this.ctx.id.toString() },
      telemetry: { functionId: "support-chat", includeRuntimeContext: { agentId: true, conversationId: true } },
    });
    return result.toUIMessageStreamResponse();
  }
}

export default {
  async fetch(request: Request, env: Env) {
    return (await routeAgentRequest(request, env)) ?? new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
