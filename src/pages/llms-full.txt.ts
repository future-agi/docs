import type { APIRoute } from 'astro';
import fs from 'fs/promises';
import path from 'path';
import { tabNavigation } from '../lib/navigation';
import type { NavItem } from '../lib/navigation';

const SITE = 'https://docs.futureagi.com';
const DOCS_DIR = path.join(process.cwd(), 'src/pages/docs');

/**
 * Generate /llms-full.txt — full documentation content for LLMs.
 * Strips frontmatter and imports, keeps markdown prose and code blocks.
 */
export const GET: APIRoute = async () => {
  const lines: string[] = [];

  lines.push('# Future AGI Documentation (Full)');
  lines.push('');
  lines.push('> Complete documentation content for Future AGI — an AI lifecycle platform for building, evaluating, observing, and optimizing AI applications.');
  lines.push('');

  // Primary source: curated navigation, in the order humans grouped them.
  const seen = new Set<string>();
  const hrefs: { title: string; href: string }[] = [];
  for (const tab of tabNavigation) {
    for (const group of tab.groups) {
      collectHrefs(group.items, hrefs);
    }
  }

  for (const { title, href } of hrefs) {
    const content = await readPageContent(href);
    if (!content) continue;
    seen.add(href);

    lines.push(`---`);
    lines.push('');
    lines.push(`## ${title}`);
    lines.push(`URL: ${SITE}${href}`);
    lines.push('');
    lines.push(content);
    lines.push('');
  }

  // Sweep src/pages/docs for any .mdx pages not already emitted. Cookbook
  // entries, release notes, FAQs, and pages added without a navigation
  // update get their full content included automatically.
  const onDisk = await walkDocsPages(DOCS_DIR);
  const additional = onDisk
    .filter(({ href }) => !seen.has(href))
    .sort((a, b) => a.href.localeCompare(b.href));

  for (const { href, title } of additional) {
    const content = await readPageContent(href);
    if (!content) continue;
    lines.push(`---`);
    lines.push('');
    lines.push(`## ${title}`);
    lines.push(`URL: ${SITE}${href}`);
    lines.push('');
    lines.push(content);
    lines.push('');
  }

  return new Response(lines.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};

async function walkDocsPages(
  dir: string,
  prefix = '/docs',
): Promise<{ href: string; title: string }[]> {
  const out: { href: string; title: string }[] = [];
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...(await walkDocsPages(full, `${prefix}/${entry.name}`)));
      continue;
    }
    if (!entry.name.endsWith('.mdx') && !entry.name.endsWith('.md')) continue;
    if (entry.name.startsWith('_')) continue;
    const stem = entry.name.replace(/\.(mdx|md)$/, '');
    const href = stem === 'index' ? prefix : `${prefix}/${stem}`;
    const title = await readTitle(full).catch(() => null);
    out.push({
      href,
      title: title || titlecase(stem === 'index' ? path.basename(prefix) : stem),
    });
  }
  return out;
}

async function readTitle(file: string): Promise<string | null> {
  const raw = await fs.readFile(file, 'utf-8');
  const match = raw.match(/^title:\s*['"]?([^'"\n]+)['"]?\s*$/m);
  return match ? match[1].trim() : null;
}

function titlecase(slug: string): string {
  return slug
    .split('-')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(' ');
}

function collectHrefs(items: NavItem[], out: { title: string; href: string }[]) {
  for (const item of items) {
    if (item.href) {
      out.push({ title: item.title, href: item.href });
    }
    if (item.items) {
      collectHrefs(item.items, out);
    }
  }
}

async function readPageContent(href: string): Promise<string | null> {
  // /docs/foo/bar → src/pages/docs/foo/bar.mdx or .../bar/index.mdx
  const relativePath = href.replace(/^\/docs\/?/, '');

  const candidates = relativePath
    ? [
        path.join(DOCS_DIR, `${relativePath}.mdx`),
        path.join(DOCS_DIR, `${relativePath}/index.mdx`),
        path.join(DOCS_DIR, `${relativePath}.md`),
      ]
    : [path.join(DOCS_DIR, 'index.mdx')];

  for (const filePath of candidates) {
    try {
      const raw = await fs.readFile(filePath, 'utf-8');
      return stripFrontmatterAndImports(raw);
    } catch {
      continue;
    }
  }
  return null;
}

function stripFrontmatterAndImports(content: string): string {
  // Remove frontmatter
  let result = content.replace(/^---[\s\S]*?---\s*/, '');

  // Remove import statements
  result = result.replace(/^import\s+.*$/gm, '');

  // Iteratively strip JSX tags (handles nesting)
  let prev = '';
  while (prev !== result) {
    prev = result;
    // Self-closing tags: <Component ... />
    result = result.replace(/<[A-Z]\w*[^>]*\/>/g, '');
    // Opening/closing paired tags — keep children
    result = result.replace(/<([A-Z]\w*)[^>]*>([\s\S]*?)<\/\1>/g, '$2');
    // Opening/closing lowercase tags like <hr />, <br />
    result = result.replace(/<(?:hr|br)\s*\/?>/gi, '');
  }

  // Remove leftover standalone closing tags
  result = result.replace(/<\/[A-Z]\w*>/g, '');
  // Remove leftover standalone opening tags (unclosed)
  result = result.replace(/<[A-Z]\w*[^>]*>/g, '');

  // Clean up excessive blank lines
  result = result.replace(/\n{3,}/g, '\n\n');

  return result.trim();
}
