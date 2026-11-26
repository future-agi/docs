import { NativeConnection, Worker } from '@temporalio/worker';
import { OpenTelemetryPlugin } from '@temporalio/interceptors-opentelemetry-v2';
import * as activities from './activities';
import { resource, sdk, spanProcessor } from './tracing';

async function main(): Promise<void> {
  sdk.start();
  try {
    const connection = await NativeConnection.connect({
      address: process.env.TEMPORAL_ADDRESS || 'localhost:7233',
    });
    try {
      const worker = await Worker.create({
        connection,
        workflowsPath: require.resolve('./workflows'),
        activities,
        taskQueue: 'weather-agent',
        plugins: [new OpenTelemetryPlugin({ resource, spanProcessor })],
      });
      await worker.run();
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
