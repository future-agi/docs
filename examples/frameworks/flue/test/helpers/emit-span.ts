// Child process for telemetry.test.ts: loads the recipe's telemetry module with
// the env the test sets, makes one OpenTelemetry span through the global API,
// and flushes through the function the module exports.
import { trace } from '@opentelemetry/api';

import { shutdownTracing } from '../../src/telemetry.ts';

trace.getTracer('flue-recipe-test').startSpan('probe').end();
await shutdownTracing();
