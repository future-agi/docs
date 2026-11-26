// Forwards /v1/responses to an upstream and rewrites the one thing a plain OpenAI backend
// rejects in @openrouter/agent's follow-up request: function_call_output items carry an id that
// starts with "output_", and OpenAI requires ids that start with "fc". OpenRouter itself accepts
// the original request, so a real OpenRouter setup does not need this file. It exists so the
// end-to-end script can use a real model that is only reachable through an OpenAI-compatible proxy.
//   node tools/responses-shim.mjs <port> <upstream-origin>
import http from 'node:http';

const [port = '18266', upstream = 'http://127.0.0.1:8317'] = process.argv.slice(2);

http
  .createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let body = Buffer.concat(chunks).toString();
    if (req.method === 'POST' && body) {
      try {
        const parsed = JSON.parse(body);
        if (Array.isArray(parsed.input)) {
          for (const item of parsed.input) {
            if (item.type === 'function_call_output' && typeof item.id === 'string' && !item.id.startsWith('fc')) delete item.id;
          }
          body = JSON.stringify(parsed);
        }
      } catch {}
    }
    const upstreamRes = await fetch(upstream + req.url, {
      method: req.method,
      headers: { authorization: req.headers.authorization ?? '', 'content-type': 'application/json' },
      body: req.method === 'POST' ? body : undefined,
    });
    res.writeHead(upstreamRes.status, { 'content-type': upstreamRes.headers.get('content-type') ?? 'application/json' });
    for await (const chunk of upstreamRes.body ?? []) res.write(chunk);
    res.end();
  })
  .listen(Number(port), '127.0.0.1');
