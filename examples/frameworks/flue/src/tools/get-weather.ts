import { defineTool } from '@flue/runtime';
import * as v from 'valibot';

// A deterministic tool, so the example needs no external service.
export const getWeather = defineTool({
  name: 'get_weather',
  description: 'Get the current weather for one city. Returns the temperature in Celsius and a short summary.',
  input: v.object({ city: v.string() }),
  async run({ data }) {
    if (/atlantis/i.test(data.city)) throw new Error(`no weather station for ${data.city}`);
    return { output: { city: data.city, temperatureC: 21, summary: 'Sunny' } };
  },
});
