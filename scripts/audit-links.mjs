#!/usr/bin/env node
/**
 * Audit navigation links against actual MDX pages.
 * Finds broken links (nav entries pointing to non-existent pages)
 * and orphan pages (pages not in navigation).
 *
 * Usage:
 *   pnpm audit-links          # Quick summary
 *   pnpm audit-links --verbose # Show all details
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const DOCS_DIR = path.join(ROOT, 'src/pages/docs');

// Dynamically import navigation (it's TypeScript, so we parse it manually)
const navFile = fs.readFileSync(path.join(ROOT, 'src/lib/navigation.ts'), 'utf-8');

// Extract all href values from navigation.ts
const navHrefs = new Set();
const hrefRegex = /href:\s*['"]([^'"]+)['"]/g;
let match;
while ((match = hrefRegex.exec(navFile)) !== null) {
  navHrefs.add(match[1]);
}

// Find all MDX pages
function findMdxPages(dir, base = '/docs') {
  const pages = new Set();
  if (!fs.existsSync(dir)) return pages;

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('_') || entry.name.startsWith('.')) continue;

    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      const sub = findMdxPages(fullPath, `${base}/${entry.name}`);
      for (const p of sub) pages.add(p);
    } else if (entry.name.endsWith('.mdx') || entry.name.endsWith('.md')) {
      const name = entry.name.replace(/\.(mdx|md)$/, '');
      if (name === 'index') {
        pages.add(base);
      } else {
        pages.add(`${base}/${name}`);
      }
    }
  }
  return pages;
}

const allPages = findMdxPages(DOCS_DIR);
const verbose = process.argv.includes('--verbose');

// Find broken nav links (href in nav but no page exists)
const broken = [];
for (const href of navHrefs) {
  if (!allPages.has(href)) {
    broken.push(href);
  }
}

// Find orphan pages (page exists but not in nav)
const orphans = [];
for (const page of allPages) {
  if (!navHrefs.has(page)) {
    orphans.push(page);
  }
}

// Sort
broken.sort();
orphans.sort();

// Output
console.log('');
console.log('  Link Audit');
console.log('  ──────────────────────────────────');
console.log(`  Nav entries:     ${navHrefs.size}`);
console.log(`  MDX pages:       ${allPages.size}`);
console.log(`  Broken links:    ${broken.length}${broken.length > 0 ? ' ✗' : ' ✓'}`);
console.log(`  Orphan pages:    ${orphans.length}${orphans.length > 0 ? ' ⚠' : ' ✓'}`);
console.log('');

if (broken.length > 0) {
  console.log('  BROKEN LINKS (in navigation but no page exists):');
  for (const href of broken) {
    console.log(`    ✗ ${href}`);
  }
  console.log('');
}

if (orphans.length > 0 && (verbose || orphans.length <= 20)) {
  console.log('  ORPHAN PAGES (page exists but not in navigation):');
  for (const page of orphans) {
    console.log(`    ⚠ ${page}`);
  }
  console.log('');
} else if (orphans.length > 20 && !verbose) {
  console.log(`  ORPHAN PAGES: ${orphans.length} pages not in navigation (use --verbose to list)`);
  console.log('');
}

// Exit code: 1 if broken links found
if (broken.length > 0) {
  process.exit(1);
}
