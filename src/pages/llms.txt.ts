import type { APIRoute } from 'astro';
import fs from 'node:fs/promises';
import path from 'node:path';
import { tabNavigation } from '../lib/navigation';
import type { NavItem } from '../lib/navigation';

const SITE = 'https://docs.futureagi.com';
const DOCS_DIR = path.join(process.cwd(), 'src/pages/docs');

/**
 * Generate /llms.txt — a concise, LLM-friendly overview of the documentation.
 * Follows the llms.txt specification: https://llmstxt.org
 *
 * Primary source is the curated tabNavigation so the human-grouped section
 * headers stay intact. After walking the nav, the script scans
 * src/pages/docs for any .mdx pages not already linked and lists them in an
 * "Additional Pages" section so cookbook entries, release notes, FAQs, and
 * any new pages added without a nav update still show up in /llms.txt.
 */
export const GET: APIRoute = async () => {
  const lines: string[] = [];
  const seen = new Set<string>();

  lines.push('# Future AGI Documentation');
  lines.push('');
  lines.push(
    '> Future AGI is an AI lifecycle platform for building, evaluating, observing, and optimizing AI applications. This documentation covers the Python SDK, platform features, integrations, and API reference.',
  );
  lines.push('');

  lines.push('## Docs');
  lines.push('');

  for (const tab of tabNavigation) {
    for (const group of tab.groups) {
      lines.push(`### ${group.group}`);
      lines.push('');
      collectLinks(group.items, lines, seen);
      lines.push('');
    }
  }

  // Walk src/pages/docs and emit anything not already linked under
  // "Additional Pages". Cookbook entries, release notes, FAQs, and pages
  // added without a nav update surface here automatically.
  const onDisk = await walkDocsPages(DOCS_DIR);
  const additional = onDisk
    .filter(({ href }) => !seen.has(href))
    .sort((a, b) => a.href.localeCompare(b.href));

  if (additional.length > 0) {
    lines.push('### Additional Pages');
    lines.push('');
    for (const { href, title } of additional) {
      lines.push(`- [${title}](${SITE}${href})`);
    }
    lines.push('');
  }

  lines.push('## Full Documentation');
  lines.push('');
  lines.push(
    `For the complete documentation with all page content, see [llms-full.txt](${SITE}/llms-full.txt).`,
  );
  lines.push('');

  return new Response(lines.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};

function collectLinks(items: NavItem[], lines: string[], seen: Set<string>) {
  for (const item of items) {
    if (item.href) {
      lines.push(`- [${item.title}](${SITE}${item.href})`);
      seen.add(item.href);
    }
    if (item.items) {
      collectLinks(item.items, lines, seen);
    }
  }
}

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
  const raw = await fs.readFile(file, 'utf8');
  const match = raw.match(/^title:\s*['"]?([^'"\n]+)['"]?\s*$/m);
  return match ? match[1].trim() : null;
}

function titlecase(slug: string): string {
  return slug
    .split('-')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(' ');
}
