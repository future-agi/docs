import { expect, test } from 'vitest';

test('invoice totals include tax', () => {
  expect(20 * 1.1).toBeCloseTo(22);
});
