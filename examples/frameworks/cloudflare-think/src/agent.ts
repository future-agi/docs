// A Think agent with one tool. Nothing in this file is about tracing: Think emits the
// invoke_agent / chat / execute_tool spans itself when `observability.traces.enabled` is true
// in wrangler.jsonc. The only tracing decision here is the two payload switches.
import { Think } from "@cloudflare/think";
import { createOpenAI } from "@ai-sdk/openai";
import { tool } from "ai";
import { z } from "zod";

export interface Env {
  WeatherAgent: DurableObjectNamespace<WeatherAgent>;
  // Any OpenAI-compatible endpoint. With Workers AI, return a "@cf/..." model id from getModel() instead.
  OPENAI_BASE_URL: string;
  OPENAI_API_KEY: string;
  MODEL: string;
  // This example's own switch for the payload opt-in (not a Cloudflare setting). See the page.
  THINK_STORE_PAYLOADS?: string;
}

export class WeatherAgent extends Think<Env> {
  // Cloudflare's default for both is false: no messages on `chat` spans, no arguments or results on
  // `execute_tool` spans. In your own agent, `override storeMessages = true` is the whole opt-in.
  override storeMessages = this.env.THINK_STORE_PAYLOADS === "true";
  override storeTools = this.env.THINK_STORE_PAYLOADS === "true";

  getModel() {
    return createOpenAI({ baseURL: this.env.OPENAI_BASE_URL, apiKey: this.env.OPENAI_API_KEY }).chat(this.env.MODEL);
  }

  getSystemPrompt() {
    return "You answer weather questions. Call the get_weather tool once, then answer in one sentence.";
  }

  getTools() {
    return {
      get_weather: tool({
        description: "Current weather for a city",
        inputSchema: z.object({ city: z.string() }),
        execute: async ({ city }) => {
          if (city.toLowerCase().includes("atlantis")) throw new Error(`no weather station for ${city}`);
          return { city, forecast: "sunny", celsius: 21 };
        },
      }),
    };
  }

  // One turn, called over Durable Object RPC from the Worker below.
  async ask(text: string) {
    const result = await this.runTurn({ input: text });
    return { status: result.status };
  }
}
