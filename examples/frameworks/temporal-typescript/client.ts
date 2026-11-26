import { randomUUID } from 'node:crypto';
import { Client, Connection } from '@temporalio/client';
import { OpenTelemetryPlugin } from '@temporalio/interceptors-opentelemetry-v2';
import { resource, sdk, spanProcessor } from './tracing';
import { weather } from './workflows';

async function main(): Promise<void> {
  sdk.start();
  try {
    const connection = await Connection.connect({
      address: process.env.TEMPORAL_ADDRESS || 'localhost:7233',
    });
    try {
      const client = new Client({
        connection,
        plugins: [new OpenTelemetryPlugin({ resource, spanProcessor })],
      });
      const result = await client.workflow.execute(weather, {
        taskQueue: 'weather-agent',
        workflowId: `weather-${randomUUID()}`,
        args: ['Oslo'],
      });
      console.log(result);
    } finally {
      await connection.close();
    }
  } finally {
    await sdk.shutdown();
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
