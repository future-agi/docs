// Trace OpenAI-client calls that go through Helicone, with Future AGI (the code the docs page shows).
//
// Two Helicone surfaces, two different auths. Keep them apart:
//   AI Gateway     baseURL https://ai-gateway.helicone.ai   apiKey = your Helicone key
//   classic proxy  baseURL https://oai.helicone.ai/v1       apiKey = your OpenAI key,
//                  header  Helicone-Auth: Bearer <your Helicone key>
//
// Future AGI keys (FI_API_KEY / FI_SECRET_KEY) are read by register() from the environment
// and go to the Future AGI collector only. Helicone keys go to Helicone only.
import { register, ProjectType } from "@traceai/fi-core";
import { OpenAIInstrumentation } from "@traceai/openai";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import * as openaiModule from "openai";
import OpenAI from "openai";

export type Surface = "gateway" | "proxy";

export const DEFAULT_BASE_URL: Record<Surface, string> = {
  gateway: "https://ai-gateway.helicone.ai",
  proxy: "https://oai.helicone.ai/v1",
};

export function setupTracing(projectName: string) {
  const tracerProvider = register({ projectType: ProjectType.OBSERVE, projectName, verbose: false });
  const instrumentation = new OpenAIInstrumentation({});
  registerInstrumentations({ instrumentations: [instrumentation], tracerProvider });
  // In an ES module the SDK is not loaded through require(), so hand the module to the
  // instrumentation explicitly. (With CommonJS, registerInstrumentations is enough.)
  instrumentation.manuallyInstrument(openaiModule as any);
  return tracerProvider;
}

export function makeClient(
  surface: Surface,
  opts: { heliconeKey: string; providerKey?: string; baseURL?: string; maxRetries?: number },
): OpenAI {
  const baseURL = opts.baseURL ?? DEFAULT_BASE_URL[surface];
  if (surface === "gateway") {
    // The Helicone key is the OpenAI apiKey. No Helicone-Auth header here.
    return new OpenAI({ baseURL, apiKey: opts.heliconeKey, maxRetries: opts.maxRetries });
  }
  if (!opts.providerKey) throw new Error("the classic proxy needs your OpenAI key as apiKey");
  return new OpenAI({
    baseURL,
    apiKey: opts.providerKey,
    defaultHeaders: { "Helicone-Auth": `Bearer ${opts.heliconeKey}` },
    maxRetries: opts.maxRetries,
  });
}
