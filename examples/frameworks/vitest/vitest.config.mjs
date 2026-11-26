import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    experimental: {
      openTelemetry: { enabled: true, sdkPath: './otel.mjs' },
    },
  },
});
