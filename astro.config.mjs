// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import react from '@astrojs/react';
import { viteDocsTransform } from './src/plugins/vite-docs-transform.mjs';

// https://astro.build/config
export default defineConfig({
  site: 'https://docs.futureagi.com',
  vite: {
    plugins: [tailwindcss(), viteDocsTransform()]
  },
  integrations: [
    react(),
    mdx(),
    sitemap()
  ],
  markdown: {
    shikiConfig: {
      theme: 'github-dark-default',
      wrap: true
    }
  }
});
