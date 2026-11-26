// A stand-in for the OpenRouter Responses endpoint. It replays two recorded streaming responses
// (tests/fixtures/*.sse, captured from a real model through an OpenAI-compatible proxy and
// scrubbed): the first asks for the get_weather tool, the second is the final answer. A model id
// of "no-such-model-for-this-demo" gets an HTTP 400. NOT a model: it is only used by the unit tests.
import http from 'node:http';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const dir = fileURLToPath(new URL('./fixtures/', import.meta.url));
const turn1 = fs.readFileSync(`${dir}turn1.sse`, 'utf8');
const turn2 = fs.readFileSync(`${dir}turn2.sse`, 'utf8');

export function startFakeResponses() {
  const requests = [];
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString() || '{}');
    requests.push({ url: req.url, body });
    if (body.model === 'no-such-model-for-this-demo') {
      res.writeHead(400, { 'content-type': 'application/json' });
      return res.end(JSON.stringify({ error: { code: 400, message: 'no such model' } }));
    }
    const followUp = Array.isArray(body.input) && body.input.some((item) => item.type === 'function_call_output');
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    res.end(followUp ? turn2 : turn1);
  });
  return new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () =>
      resolve({
        url: `http://127.0.0.1:${server.address().port}/v1`,
        requests,
        close: () => new Promise((done) => server.close(done)),
      }),
    ),
  );
}
