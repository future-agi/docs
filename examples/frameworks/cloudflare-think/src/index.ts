// Worker entry: POST /turn?conversation=<id> with {"text": "..."} runs one Think turn.
// One conversation id = one Durable Object = one gen_ai.conversation.id in the traces.
import { tracing } from "cloudflare:workers";
import { getAgentByName } from "agents";
import { WeatherAgent, type Env } from "./agent";

export { WeatherAgent };

export default {
  async fetch(request: Request, env: Env) {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/turn") return new Response("not found", { status: 404 });
    const conversation = url.searchParams.get("conversation") || "default";
    const { text } = (await request.json()) as { text?: string };
    if (!text) return new Response("text is required", { status: 400 });
    // Optional, recommended: put the conversation on the Worker's request span, the root of the trace,
    // so Future AGI links the whole trace (not only Think's spans) to the conversation's session.
    // Think's own spans carry the same value: the Durable Object id.
    tracing.getActiveSpan()?.setAttribute("gen_ai.conversation.id", env.WeatherAgent.idFromName(conversation).toString());
    const agent = await getAgentByName(env.WeatherAgent, conversation);
    return Response.json(await agent.ask(text));
  },
} satisfies ExportedHandler<Env>;
