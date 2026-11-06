// Local OTLP/HTTP recorder for tests and the E2E script. It saves every request
// (headers with secrets masked, raw body, decoded spans) and optionally forwards
// it unchanged to FORWARD so the same bytes also reach a real collector.
//   node scripts/recorder.mjs --port 4319 --out ./recorded [--forward http://localhost:14338]
import { createServer } from "node:http";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { decodeTraceRequest } from "./otlp-decode.mjs";

const SECRET_HEADER = /key|secret|authorization/i;

export function startRecorder({ port = 0, out, forward } = {}) {
  if (out) mkdirSync(out, { recursive: true });
  const requests = [];
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const headers = { ...req.headers };
    const masked = {};
    for (const [k, v] of Object.entries(headers)) {
      masked[k] = SECRET_HEADER.test(k) ? `<set:${String(v).length} chars>` : v;
    }
    let spans = [];
    let decodeError = null;
    try { spans = decodeTraceRequest(body); } catch (e) { decodeError = String(e); }
    const record = { at: new Date().toISOString(), method: req.method, url: req.url, headers: masked, bodyBytes: body.length, decodeError, spans };
    let status = 200;
    let reply = "";
    let contentType = "application/x-protobuf";
    if (forward) {
      try {
        const r = await fetch(forward.replace(/\/+$/, "") + req.url, {
          method: "POST",
          headers: Object.fromEntries(Object.entries(headers).filter(([k]) => !["host", "content-length", "connection", "transfer-encoding"].includes(k))),
          body,
        });
        status = r.status;
        reply = await r.text();
        contentType = r.headers.get("content-type") ?? contentType;
        record.forwardStatus = r.status;
        if (r.status >= 300) record.forwardBody = reply.slice(0, 500);
      } catch (e) {
        status = 502;
        reply = String(e);
        record.forwardStatus = 502;
        record.forwardBody = reply.slice(0, 500);
      }
    }
    requests.push({ ...record, rawHeaders: headers, body });
    if (out) {
      const n = String(requests.length).padStart(3, "0");
      writeFileSync(join(out, `req-${n}.bin`), body);
      writeFileSync(join(out, `req-${n}.json`), JSON.stringify(record, (_k, v) => (typeof v === "bigint" ? v.toString() : v), 1));
    }
    res.writeHead(status, { "content-type": contentType });
    res.end(reply);
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({ server, port: server.address().port, requests })));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
  const { port } = await startRecorder({ port: Number(arg("port", "4319")), out: arg("out", "./recorded"), forward: arg("forward") });
  console.log(`recorder listening on http://127.0.0.1:${port}`);
}
