// No network, no Cloudflare, no wrangler. A fake env.AI, a fake ctx and a fake exporter / fake fetch.
import { describe, expect, it } from "vitest";
import type { ReadableSpan, SpanExporter } from "@opentelemetry/sdk-trace-base";
import { createTracing, fiExporter } from "../src/tracing";
import { handle, MODEL, type Env } from "../src/index";

const KEYS = { FI_API_KEY: "k-test", FI_SECRET_KEY: "s-test", FI_PROJECT_NAME: "unit-proj" };
const ctx = { waitUntil: () => {} };

/** Records what reached the exporter and when, relative to the Response being returned. */
function fakeExporter() {
  const batches: ReadableSpan[][] = [];
  const exporter: SpanExporter = {
    export(spans, done) {
      batches.push([...spans]);
      done({ code: 0 });
    },
    shutdown: async () => {},
  };
  return { batches, exporter, spans: () => batches.flat() };
}

function envWith(ai: Env["AI"], extra: Record<string, string> = {}): Env {
  return { AI: ai, ...KEYS, ...extra };
}
const okAi = (result: unknown = { response: "hi", usage: { prompt_tokens: 7, completion_tokens: 3, total_tokens: 10 } }) => ({
  run: async () => result,
});

async function call(env: Env, url = "https://w.example/chat", prompt = "hello") {
  return handle(new Request(url, { method: "POST", body: JSON.stringify({ prompt }) }), env, ctx);
}

// handle() builds its own tracing from env, so these tests drive it through a fake fetch that the real exporter uses.
function withFakeFetch<T>(fn: (calls: { url: string; init: RequestInit }[]) => Promise<T>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const orig = globalThis.fetch;
  globalThis.fetch = (async (url: any, init: any) => {
    calls.push({ url: String(url), init });
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
  return fn(calls).finally(() => {
    globalThis.fetch = orig;
  });
}
const decode = (init: RequestInit) => JSON.parse(new TextDecoder().decode(init.body as Uint8Array));
const spansOf = (req: any) => req.resourceSpans.flatMap((r: any) => r.scopeSpans.flatMap((s: any) => s.spans));
const attr = (list: any[], k: string) => list.find((a) => a.key === k)?.value;

describe("flush before the Response returns (AC-02, AC-03)", () => {
  it("success: one root and one AI child are exported before handle() resolves", async () => {
    await withFakeFetch(async (calls) => {
      const res = await call(envWith(okAi()));
      expect(res.status).toBe(200);
      expect(calls).toHaveLength(1); // already sent when the Response is in hand
      const spans = spansOf(decode(calls[0].init));
      expect(spans.map((s: any) => s.name).sort()).toEqual(["worker.fetch", "workers_ai.run"]);
      const root = spans.find((s: any) => s.name === "worker.fetch");
      const child = spans.find((s: any) => s.name === "workers_ai.run");
      expect(child.parentSpanId).toBe(root.spanId);
      expect(child.traceId).toBe(root.traceId);
      expect(root.parentSpanId ?? "").toBe("");
    });
  });

  it("AI error: child is ERROR, root is ERROR for a 502, still flushed before return (AC-02)", async () => {
    await withFakeFetch(async (calls) => {
      const res = await call(envWith({ run: async () => { throw new Error("boom with secret-marker"); } }));
      expect(res.status).toBe(502);
      expect(calls).toHaveLength(1);
      const spans = spansOf(decode(calls[0].init));
      for (const s of spans) expect(s.status.code).toBe(2); // ERROR
      // default: only the error class, never the raw message
      expect(JSON.stringify(spans)).not.toContain("secret-marker");
      expect(spans.find((s: any) => s.name === "workers_ai.run").status.message).toBe("Error");
    });
  });
});

describe("attributes", () => {
  it("model id comes from the argument; usage present when the binding returned it (AC-04)", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi()));
      const child = spansOf(decode(calls[0].init)).find((s: any) => s.name === "workers_ai.run");
      expect(attr(child.attributes, "gen_ai.request.model")).toEqual({ stringValue: MODEL });
      expect(attr(child.attributes, "gen_ai.usage.input_tokens")).toEqual({ intValue: 7 });
      expect(attr(child.attributes, "gen_ai.usage.output_tokens")).toEqual({ intValue: 3 });
      expect(attr(child.attributes, "gen_ai.provider.name")).toEqual({ stringValue: "cloudflare" });
      expect(attr(child.attributes, "gen_ai.system")).toBeUndefined(); // one provider key
    });
  });

  it("usage omitted, not zero-filled, when the result has none (AC-05)", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi({ response: "hi" })));
      const child = spansOf(decode(calls[0].init)).find((s: any) => s.name === "workers_ai.run");
      const keys = child.attributes.map((a: any) => a.key);
      expect(keys.some((k: string) => k.includes("token"))).toBe(false);
    });
  });

  it("query string is not copied onto any span (AC-07)", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi()), "https://w.example/chat?token=query-secret-1");
      const raw = JSON.stringify(decode(calls[0].init));
      expect(raw).not.toContain("query-secret-1");
      expect(raw).toContain("/chat");
    });
  });
});

describe("privacy (AC-06)", () => {
  it("default export carries no prompt and no response", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi({ response: "answer-marker-xyz", usage: undefined })), undefined, "prompt-marker-xyz");
      const raw = JSON.stringify(decode(calls[0].init));
      expect(raw).not.toContain("prompt-marker-xyz");
      expect(raw).not.toContain("answer-marker-xyz");
    });
  });
  it("FI_CAPTURE_CONTENT=true turns prompt and response on", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi({ response: "answer-marker-xyz" }), { FI_CAPTURE_CONTENT: "true" }), undefined, "prompt-marker-xyz");
      const raw = JSON.stringify(decode(calls[0].init));
      expect(raw).toContain("prompt-marker-xyz");
      expect(raw).toContain("answer-marker-xyz");
    });
  });
});

describe("missing keys and failing export never change the response (AC-08)", () => {
  it("unset keys: application status, nothing exported, no throw", async () => {
    await withFakeFetch(async (calls) => {
      const res = await call({ AI: okAi() } as Env);
      expect(res.status).toBe(200);
      expect(calls).toHaveLength(0);
    });
  });
  it("one key missing is treated as off", async () => {
    await withFakeFetch(async (calls) => {
      const res = await call(envWith(okAi(), { FI_SECRET_KEY: "" }));
      expect(res.status).toBe(200);
      expect(calls).toHaveLength(0);
    });
  });
  it("collector error and network failure leave the response alone", async () => {
    const orig = globalThis.fetch;
    try {
      globalThis.fetch = (async () => new Response("no", { status: 500 })) as typeof fetch;
      expect((await call(envWith(okAi()))).status).toBe(200);
      globalThis.fetch = (async () => { throw new TypeError("network"); }) as typeof fetch;
      expect((await call(envWith(okAi()))).status).toBe(200);
    } finally {
      globalThis.fetch = orig;
    }
  });
  it("a hung collector is bounded by the flush budget", async () => {
    const orig = globalThis.fetch;
    try {
      globalThis.fetch = ((_u: any, init: any) => new Promise((_r, rej) => init.signal.addEventListener("abort", () => rej(new Error("aborted"))))) as typeof fetch;
      const t0 = Date.now();
      const res = await call(envWith(okAi()));
      expect(res.status).toBe(200);
      expect(Date.now() - t0).toBeLessThan(3500);
    } finally {
      globalThis.fetch = orig;
    }
  });
});

describe("what the exporter sends (AC-09)", () => {
  it("both headers, no content-encoding, /tracer/v1/traces, resource project_name + project_type", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi(), { FI_BASE_URL: "https://fi.example.test/" }));
      const { url, init } = calls[0];
      expect(url).toBe("https://fi.example.test/tracer/v1/traces");
      const h = init.headers as Record<string, string>;
      expect(h["X-Api-Key"]).toBe("k-test");
      expect(h["X-Secret-Key"]).toBe("s-test");
      expect(Object.keys(h).map((k) => k.toLowerCase())).not.toContain("content-encoding");
      const res = decode(init).resourceSpans[0].resource.attributes;
      expect(attr(res, "project_name")).toEqual({ stringValue: "unit-proj" });
      expect(attr(res, "project_type")).toEqual({ stringValue: "observe" });
    });
  });
  it("keys never appear in the exported spans", async () => {
    await withFakeFetch(async (calls) => {
      await call(envWith(okAi()));
      const raw = JSON.stringify(decode(calls[0].init));
      expect(raw).not.toContain("k-test");
      expect(raw).not.toContain("s-test");
    });
  });
});

describe("tracing helper with a fake exporter", () => {
  it("flush() exports both spans in one batch; disabled tracing flushes to true", async () => {
    const f = fakeExporter();
    const t = createTracing(KEYS, f.exporter);
    const root = t.startSpan("a", {});
    const child = t.startSpan("b", {}, root);
    child.end();
    root.end();
    expect(f.batches).toHaveLength(0); // nothing leaves on a timer
    expect(await t.flush()).toBe(true);
    expect(f.batches).toHaveLength(1);
    expect(f.spans().map((s) => s.name).sort()).toEqual(["a", "b"]);
    expect(fiExporter({})).toBeUndefined();
    expect(await createTracing({}).flush()).toBe(true);
  });
});
