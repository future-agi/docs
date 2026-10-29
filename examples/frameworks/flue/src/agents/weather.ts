'use agent';
import { useModel, useTool } from '@flue/runtime';

import '../telemetry.ts'; // `flue run` loads this module, not app.ts
import { MODEL } from '../model.ts';
import { getWeather } from '../tools/get-weather.ts';

export function Weather() {
  useModel(MODEL);
  useTool(getWeather);
  return 'You are a weather assistant. Always call get_weather for the city the user names, then answer in one sentence that repeats the city name exactly as the user wrote it.';
}
