#!/usr/bin/env node
/**
 * Comprehensive link audit:
 *  1. Broken nav links (nav href → no page)
 *  2. Broken internal links (MDX content links → no page)
 *  3. Orphan pages (page exists but not in nav)
 *
 * Usage:
 *   pnpm audit-links              # Summary + broken links
 *   pnpm audit-links --verbose    # Also show orphan pages
 *   pnpm audit-links --fix        # Suggest fixes
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PAGES_DIR = path.join(ROOT, 'src/pages');
const DOCS_DIR = path.join(PAGES_DIR, 'docs');

const verbose = process.argv.includes('--verbose');

// ── 1. Discover all actual pages ──────────────────────────────
function findPages(dir, base = '') {
  const pages = new Set();
  if (!fs.existsSync(dir)) return pages;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('_') || entry.name.startsWith('.')) continue;
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      for (const p of findPages(fullPath, `${base}/${entry.name}`)) pages.add(p);
    } else if (/\.(mdx|md|astro)$/.test(entry.name)) {
      const name = entry.name.replace(/\.(mdx|md|astro)$/, '');
      pages.add(name === 'index' ? (base || '/') : `${base}/${name}`);
    }
  }
  return pages;
}

const allPages = findPages(PAGES_DIR);

function pageExists(href) {
  // Normalize: strip trailing slash, anchors, query params
  let h = href.split('#')[0].split('?')[0].replace(/\/$/, '') || '/';
  return allPages.has(h);
}

// ── 2. Extract nav hrefs ──────────────────────────────────────
const navFile = fs.readFileSync(path.join(ROOT, 'src/lib/navigation.ts'), 'utf-8');
const navHrefs = new Map(); // href → line number
const hrefRegex = /href:\s*['"]([^'"]+)['"]/g;
let match;
const navLines = navFile.split('\n');
while ((match = hrefRegex.exec(navFile)) !== null) {
  const lineNum = navFile.substring(0, match.index).split('\n').length;
  navHrefs.set(match[1], lineNum);
}

// ── 3. Extract all internal links from MDX files ──────────────
function findMdxFiles(dir) {
  const files = [];
  if (!fs.existsSync(dir)) return files;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('_') || entry.name.startsWith('.')) continue;
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...findMdxFiles(fullPath));
    else if (/\.(mdx|md)$/.test(entry.name)) files.push(fullPath);
  }
  return files;
}

const contentBroken = []; // { file, line, href }
const imageExts = /\.(png|jpg|jpeg|gif|svg|webp|ico)$/i;
const linkRegex = /(?:\[.*?\]\(|href=["'])(\/?docs\/[^)"'\s#]+)/g;

for (const file of findMdxFiles(DOCS_DIR)) {
  const content = fs.readFileSync(file, 'utf-8');
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    let m;
    linkRegex.lastIndex = 0;
    while ((m = linkRegex.exec(lines[i])) !== null) {
      let href = m[1];
      // Skip image/asset paths
      if (imageExts.test(href)) continue;
      // Normalize: ensure leading slash
      if (!href.startsWith('/')) href = '/' + href;
      if (!pageExists(href)) {
        const relFile = path.relative(ROOT, file);
        contentBroken.push({ file: relFile, line: i + 1, href });
      }
    }
  }
}

// ── 4. Find broken nav links ──────────────────────────────────
const navBroken = [];
for (const [href, line] of navHrefs) {
  let h = href;
  if (!h.startsWith('/')) h = '/' + h;
  if (!pageExists(h)) {
    navBroken.push({ href, line });
  }
}

// ── 5. Find orphan pages ──────────────────────────────────────
const navHrefSet = new Set();
for (const href of navHrefs.keys()) {
  navHrefSet.add(href.startsWith('/') ? href : '/' + href);
}
const orphans = [];
for (const page of allPages) {
  if (page.startsWith('/docs') && !navHrefSet.has(page)) {
    orphans.push(page);
  }
}

// ── Output ────────────────────────────────────────────────────
navBroken.sort((a, b) => a.href.localeCompare(b.href));
contentBroken.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
orphans.sort();

const totalBroken = navBroken.length + contentBroken.length;

console.log('');
console.log('  Link Audit');
console.log('  ──────────────────────────────────────────────');
console.log(`  Pages found:         ${allPages.size}`);
console.log(`  Nav entries:         ${navHrefs.size}`);
console.log(`  Broken nav links:    ${navBroken.length}${navBroken.length ? ' ✗' : ' ✓'}`);
console.log(`  Broken content links:${contentBroken.length.toString().padStart(5)}${contentBroken.length ? ' ✗' : ' ✓'}`);
console.log(`  Orphan pages:        ${orphans.length}${orphans.length ? ' ⚠' : ' ✓'}`);
console.log('');

if (navBroken.length > 0) {
  console.log('  BROKEN NAV LINKS (navigation.ts → no page):');
  for (const { href, line } of navBroken) {
    console.log(`    ✗ ${href}  (navigation.ts:${line})`);
  }
  console.log('');
}

if (contentBroken.length > 0) {
  // Deduplicate by href for summary
  const byHref = new Map();
  for (const b of contentBroken) {
    if (!byHref.has(b.href)) byHref.set(b.href, []);
    byHref.get(b.href).push(b);
  }
  console.log(`  BROKEN CONTENT LINKS (${byHref.size} unique dead links in ${contentBroken.length} references):`);
  for (const [href, refs] of [...byHref.entries()].slice(0, verbose ? Infinity : 30)) {
    console.log(`    ✗ ${href}`);
    if (verbose) {
      for (const r of refs) {
        console.log(`        └─ ${r.file}:${r.line}`);
      }
    }
  }
  if (!verbose && byHref.size > 30) {
    console.log(`    ... and ${byHref.size - 30} more (use --verbose)`);
  }
  console.log('');
}

if (orphans.length > 0) {
  if (verbose) {
    console.log('  ORPHAN PAGES (exist but not in navigation):');
    for (const page of orphans) {
      console.log(`    ⚠ ${page}`);
    }
  } else {
    console.log(`  ORPHAN PAGES: ${orphans.length} pages not in nav (use --verbose to list)`);
  }
  console.log('');
}

if (totalBroken > 0) process.exit(1);
