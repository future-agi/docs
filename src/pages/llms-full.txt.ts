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

  // Collect all hrefs from navigation
  const hrefs: { title: string; href: string }[] = [];
  for (const tab of tabNavigation) {
    for (const group of tab.groups) {
      collectHrefs(group.items, hrefs);
    }
  }

  // For each page, read the MDX and extract content
  for (const { title, href } of hrefs) {
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
