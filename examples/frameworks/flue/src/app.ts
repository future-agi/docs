import './telemetry.ts'; // first import: the SDK and Flue's instrumentation are installed before any agent runs
import { createAgentRouter } from '@flue/runtime/routing';
import { Hono } from 'hono';

import { Weather } from './agents/weather.ts';

const app = new Hono();
app.route('/agents/weather', createAgentRouter(Weather));

export default app;
