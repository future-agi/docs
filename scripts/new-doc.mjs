#!/usr/bin/env node

/**
 * Scaffold a new documentation page and add it to navigation.
 *
 * Usage:
 *   pnpm new-doc <path> [title]
 *
 * Examples:
 *   pnpm new-doc docs/evaluation/my-eval "My Custom Eval"
 *   pnpm new-doc docs/tracing/auto/newprovider "New Provider"
 *   pnpm new-doc docs/dataset/concepts/overview
 */

import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);

if (args.length === 0 || args[0] === '--help' || args[0] === '-h') {
  console.log(`
  Usage: pnpm new-doc <path> [title]

  Creates a new MDX doc page and adds it to navigation.

  Arguments:
    path    Page path relative to site root (e.g., docs/evaluation/my-eval)
    title   Optional page title (defaults to filename in Title Case)

  Examples:
    pnpm new-doc docs/evaluation/my-eval "My Custom Eval"
    pnpm new-doc docs/tracing/auto/newprovider
    pnpm new-doc docs/cookbook/my-recipe "My Recipe"
  `);
  process.exit(0);
}

// Parse arguments
const rawPath = args[0].replace(/^\//, '').replace(/\.mdx$/, '');
const title = args[1] || toTitleCase(path.basename(rawPath));

const filePath = path.join('src/pages', rawPath + '.mdx');
const urlPath = '/' + rawPath;

// Check if file already exists
if (fs.existsSync(filePath)) {
  console.error(`\x1b[31mError:\x1b[0m File already exists: ${filePath}`);
  process.exit(1);
}

// Create directory if needed
fs.mkdirSync(path.dirname(filePath), { recursive: true });

// Generate MDX content (minimal — plugin handles layout + imports)
const content = `---
title: "${title}"
description: ""
---

## ${title}

Content goes here.
`;

fs.writeFileSync(filePath, content);
console.log(`\x1b[32m✓\x1b[0m Created ${filePath}`);

// Try to add to navigation
const navResult = addToNavigation(urlPath, title);
if (navResult) {
  console.log(`\x1b[32m✓\x1b[0m Added to navigation: ${urlPath}`);
} else {
  console.log(`\x1b[33m!\x1b[0m Could not auto-add to navigation.`);
  console.log(`  Add this line to src/lib/navigation.ts in the appropriate group:`);
  console.log(`  { title: '${title}', href: '${urlPath}' },`);
}

console.log(`\n  URL: http://localhost:4321${urlPath}`);

// --- Helpers ---

function toTitleCase(str) {
  return str
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Find the right place in navigation.ts and insert the new page entry.
 * Strategy: find the last href that shares the same parent path, insert after it.
 */
function addToNavigation(href, title) {
  const navPath = 'src/lib/navigation.ts';
  if (!fs.existsSync(navPath)) return false;

  let navContent = fs.readFileSync(navPath, 'utf8');
  const parentPath = path.dirname(href).replace(/\\/g, '/');

  // Find all lines with href entries matching the parent path
  const lines = navContent.split('\n');
  let lastMatchIndex = -1;
  let matchIndent = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // Match lines like: { title: '...', href: '/docs/evaluation/...' },
    const hrefMatch = line.match(/^(\s*).*href:\s*'([^']+)'/);
    if (hrefMatch) {
      const lineHref = hrefMatch[2];
      const lineParent = path.dirname(lineHref).replace(/\\/g, '/');
      if (lineParent === parentPath || lineHref === parentPath) {
        lastMatchIndex = i;
        matchIndent = hrefMatch[1];
      }
    }
  }

  if (lastMatchIndex === -1) return false;

  // Find the end of this entry (could span multiple lines if it has items)
  let insertIndex = lastMatchIndex;

  // If the matched line ends with },  we can insert right after
  // If it has items: [...], we need to find the closing }
  const matchedLine = lines[lastMatchIndex];
  if (matchedLine.includes('items:') || matchedLine.trim().endsWith('{')) {
    // Find closing brace at same indent level
    let braceDepth = 0;
    for (let i = lastMatchIndex; i < lines.length; i++) {
      for (const ch of lines[i]) {
        if (ch === '{' || ch === '[') braceDepth++;
        if (ch === '}' || ch === ']') braceDepth--;
      }
      if (braceDepth <= 0) {
        insertIndex = i;
        break;
      }
    }
  }

  // Build the new entry line
  const newEntry = `${matchIndent}{ title: '${title}', href: '${href}' },`;

  // Insert after the matched entry
  lines.splice(insertIndex + 1, 0, newEntry);
  fs.writeFileSync(navPath, lines.join('\n'));
  return true;
}
