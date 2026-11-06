// Tiny stdio MCP server used by the LibreChat recipe test run.
//
// LibreChat starts it with `node /mcp/order_tools.mjs` (see librechat.yaml). It imports the MCP SDK
// that ships inside the LibreChat image, so nothing extra is installed. Two tools:
//   get_order_status(order_id)  returns a fixed status for any order id
//   cancel_order(order_id)      always fails, to produce a tool error in the trace
// The tools never read files, the network or the environment.
import { McpServer } from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/server/mcp.js';
import { StdioServerTransport } from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js';
import { z } from '/app/node_modules/zod/dist/esm/index.js';

const server = new McpServer({ name: 'order-tools', version: '1.0.0' });

server.tool(
  'get_order_status',
  'Look up the shipping status of an order by its id.',
  { order_id: z.string().describe('Order id, for example A-1001') },
  async ({ order_id }) => ({
    content: [
      {
        type: 'text',
        text: JSON.stringify({ order_id, status: 'shipped', carrier: 'DemoPost', eta_days: 2 }),
      },
    ],
  }),
);

server.tool(
  'cancel_order',
  'Cancel an order by its id.',
  { order_id: z.string().describe('Order id') },
  async () => {
    throw new Error('cancellation service unavailable');
  },
);

await server.connect(new StdioServerTransport());
