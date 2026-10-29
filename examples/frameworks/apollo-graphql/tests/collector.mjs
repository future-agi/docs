// A tiny OTLP/HTTP trace collector for the tests: records headers and decoded JSON bodies.
import http from "node:http";

export async function startCollector() {
  const requests = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const raw = Buffer.concat(chunks);
      let body = null;
      try { body = JSON.parse(raw.toString("utf8")); } catch { /* keep null */ }
      requests.push({ method: req.method, path: req.url, headers: req.headers, body, rawLength: raw.length });
      res.writeHead(200, { "content-type": "application/json" });
      res.end("{}");
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}`,
    requests,
    close: () => new Promise((r) => server.close(r)),
    resourceAttributes() {
      const map = {};
      for (const req of requests) for (const rs of req.body?.resourceSpans ?? []) for (const a of rs.resource?.attributes ?? []) map[a.key] = a.value?.stringValue;
      return map;
    },
    spans() {
      const out = [];
      for (const req of requests) for (const rs of req.body?.resourceSpans ?? []) for (const ss of rs.scopeSpans ?? []) for (const s of ss.spans ?? []) {
        const attributes = {};
        for (const a of s.attributes ?? []) attributes[a.key] = a.value?.stringValue ?? a.value?.intValue ?? a.value?.boolValue ?? a.value;
        out.push({ ...s, attributes, scope: ss.scope?.name });
      }
      return out;
    },
  };
}
