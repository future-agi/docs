/**
 * Checks that every MDX page deleted in this branch has a corresponding
 * entry in src/lib/redirects.ts. Fails with exit code 1 if any are missing.
 *
 * Usage: node scripts/check-deleted-pages.mjs [base-branch]
 * Default base branch: dev
 */
import { execSync } from 'child_process';
import { readFileSync } from 'fs';

const baseBranch = process.argv[2] || 'dev';

// Get deleted MDX files compared to base branch
let deletedFiles;
try {
  const output = execSync(
    `git diff origin/${baseBranch}...HEAD --name-only --diff-filter=D`,
    { encoding: 'utf-8' }
  );
  deletedFiles = output.trim().split('\n').filter(Boolean);
} catch {
  // If origin/base doesn't exist, try without origin/
  try {
    const output = execSync(
      `git diff ${baseBranch}...HEAD --name-only --diff-filter=D`,
      { encoding: 'utf-8' }
    );
    deletedFiles = output.trim().split('\n').filter(Boolean);
  } catch {
    console.error('Could not determine deleted files — failing to surface the error.');
    process.exit(1);
  }
}

// Filter to only MDX pages under src/pages/
const deletedPages = deletedFiles.filter(f => f.startsWith('src/pages/') && f.endsWith('.mdx'));

if (deletedPages.length === 0) {
  console.log('No MDX pages deleted in this branch. ✓');
  process.exit(0);
}

// Convert file path to URL path
function fileToPath(file) {
  return file
    .replace(/^src\/pages/, '')
    .replace(/\.mdx$/, '')
    .replace(/\/index$/, '') || '/';
}

// Load redirects map
const redirectsRaw = readFileSync('src/lib/redirects.ts', 'utf-8');
const redirectEntries = [...redirectsRaw.matchAll(/["']([^"']+)["']:\s*["']([^"']+)["']/g)];
const redirectMap = new Set(redirectEntries.map(([, from]) => from));

// Check each deleted page
const missing = [];
for (const file of deletedPages) {
  const urlPath = fileToPath(file);
  if (!redirectMap.has(urlPath)) {
    missing.push({ file, urlPath });
  }
}

if (missing.length === 0) {
  console.log(`All ${deletedPages.length} deleted page(s) have redirects. ✓`);
  process.exit(0);
}

console.error(`\n✗ ${missing.length} deleted page(s) have no redirect in src/lib/redirects.ts:\n`);
for (const { file, urlPath } of missing) {
  console.error(`  ${urlPath}`);
  console.error(`    (deleted file: ${file})`);
}
console.error(`
To fix: add an entry to src/lib/redirects.ts for each path above, pointing to the closest current page.
Example:  '${missing[0].urlPath}': '/docs/some-current-page',
`);
process.exit(1);
