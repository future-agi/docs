// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import react from '@astrojs/react';
import { viteDocsTransform } from './src/plugins/vite-docs-transform.mjs';
import compression from 'vite-plugin-compression';
import { existsSync, readFileSync } from 'node:fs';
import { redirectMap } from './src/lib/redirects.ts';

// Astro's own redirects. None today; add any here so they stay out of the sitemap too.
const redirects = {};

const normalizePath = (path) => decodeURIComponent(path).replace(/\/+$/, '') || '/';
const redirectSources = new Set(
  [...Object.keys(redirectMap), ...Object.keys(redirects)].map(normalizePath)
);

// A redirect key can share its path with a real page, which then wins the route
// (e.g. /docs/sdk/tracing). Keep those in the sitemap, unless the page file is an
// .astro file that only redirects.
const isPageFile = (path) => {
  const base = `./src/pages${path === '/' ? '' : path}`;
  return ['.mdx', '.md', '.astro', '/index.mdx', '/index.md', '/index.astro'].some((ext) => {
    const file = new URL(`${base}${ext}`, import.meta.url);
    if (!existsSync(file)) return false;
    return !ext.endsWith('.astro') || !/\bAstro\.redirect\(/.test(readFileSync(file, 'utf-8'));
  });
};

// Leave redirect stubs out of the sitemap so it lists only pages with content
const isSitemapPage = (page) => {
  const path = normalizePath(new URL(page).pathname);
  return !redirectSources.has(path) || isPageFile(path);
};

// https://astro.build/config
export default defineConfig({
  site: 'https://docs.futureagi.com',
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'viewport',
  },
  redirects,
  // Optimize build output
  compressHTML: true,
  vite: {
    plugins: [tailwindcss(), viteDocsTransform(), compression({ algorithm: 'gzip' })]
  },
  integrations: [
    react(),
    mdx(),
    sitemap({ filter: isSitemapPage })
  ],
  markdown: {
    shikiConfig: {
      theme: 'github-dark-default',
      wrap: true
    }
  }
});
