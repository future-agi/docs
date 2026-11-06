// A standalone Flue workflow: boots the runtime in this process (no server, no
// app.ts), asks the agent one question and prints the submission id and reply.
//   node scripts/ask.ts 'Use get_weather for the city "Paris".'
import { init } from '@flue/runtime';
import { start } from '@flue/runtime/node';

import { Weather } from '../src/agents/weather.ts';

const flue = await start({ agents: [Weather] });
try {
  const weather = init(Weather, { id: `ask-${Date.now()}` });
  const receipt = await weather.dispatch(process.argv[2] ?? 'What is the weather in Paris?');
  const reply = await weather.read(receipt);
  console.log(JSON.stringify({ submissionId: receipt.submissionId, text: reply.text }));
} finally {
  // Equivalent to `await using`, whose syntax is not supported on Node 22.
  await flue[Symbol.asyncDispose]();
}
