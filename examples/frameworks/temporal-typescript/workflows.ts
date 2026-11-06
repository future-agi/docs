import { proxyActivities } from '@temporalio/workflow';
import type * as activities from './activities';

const { forecast } = proxyActivities<typeof activities>({ startToCloseTimeout: '1 minute' });

export async function weather(city: string): Promise<string> {
  return await forecast(city);
}
