import type { APIRoute } from 'astro';
import { tabNavigation } from '../lib/navigation';
import fs from 'fs';
import path from 'path';

interface SearchEntry {
  title: string;
  href: string;
  group: string;
  tab: string;
  description: string;
  headings: string[];
}

function extractFrontmatter(content: string): { title?: string; description?: string } {
  const match = content.match(/^---\n([\s\S]*?)\n---/);
  if (!match) return {};
  const fm: Record<string, string> = {};
  for (const line of match[1].split('\n')) {
    const [key, ...rest] = line.split(':');
    if (key && rest.length) {
      fm[key.trim()] = rest.join(':').trim().replace(/^["']|["']$/g, '');
    }
  }
  return fm;
}

function extractHeadings(content: string): string[] {
  const headings: string[] = [];
  const regex = /^#{2,3}\s+(.+)$/gm;
  let match;
  while ((match = regex.exec(content)) !== null) {
    headings.push(match[1].trim());
  }
  return headings;
}

function flattenItems(items: any[], group: string, tab: string, out: SearchEntry[]) {
  for (const item of items) {
    if (item.href) {
      // Try to read the MDX file and extract description + headings
      let description = '';
      let headings: string[] = [];
      try {
        const filePath = item.href.replace(/^\//, '') + '.mdx';
        const fullPath = path.resolve('src/pages', filePath);
        if (fs.existsSync(fullPath)) {
          const content = fs.readFileSync(fullPath, 'utf-8');
          const fm = extractFrontmatter(content);
          description = fm.description || '';
          headings = extractHeadings(content);
        } else {
          // Try index.mdx
          const indexPath = path.resolve('src/pages', item.href.replace(/^\//, ''), 'index.mdx');
          if (fs.existsSync(indexPath)) {
            const content = fs.readFileSync(indexPath, 'utf-8');
            const fm = extractFrontmatter(content);
            description = fm.description || '';
            headings = extractHeadings(content);
          }
        }
      } catch {}
      out.push({ title: item.title, href: item.href, group, tab, description, headings });
    }
    if (item.items) flattenItems(item.items, group, tab, out);
  }
}

export const GET: APIRoute = () => {
  const entries: SearchEntry[] = [];
  for (const tab of tabNavigation) {
    for (const group of tab.groups) {
      flattenItems(group.items, group.group, tab.tab, entries);
    }
  }
  return new Response(JSON.stringify(entries), {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
