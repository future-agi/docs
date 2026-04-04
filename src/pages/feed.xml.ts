import type { APIRoute } from 'astro';
import fs from 'fs';
import path from 'path';
import { tabNavigation } from '../lib/navigation';

const SITE = 'https://docs.futureagi.com';

interface PageInfo {
  title: string;
  href: string;
  description: string;
  lastModified: string;
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

function collectPages(items: any[], out: PageInfo[]) {
  for (const item of items) {
    if (item.href) {
      const filePath = item.href.replace(/^\//, '') + '.mdx';
      const fullPath = path.resolve('src/pages', filePath);
      const indexPath = path.resolve('src/pages', item.href.replace(/^\//, ''), 'index.mdx');

      let description = '';
      let lastModified = new Date().toISOString();

      for (const p of [fullPath, indexPath]) {
        try {
          if (fs.existsSync(p)) {
            const content = fs.readFileSync(p, 'utf-8');
            const fm = extractFrontmatter(content);
            description = fm.description || '';
            const stat = fs.statSync(p);
            lastModified = stat.mtime.toISOString();
            break;
          }
        } catch {}
      }

      out.push({
        title: item.title,
        href: item.href,
        description,
        lastModified,
      });
    }
    if (item.items) collectPages(item.items, out);
  }
}

function escapeXml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export const GET: APIRoute = () => {
  const pages: PageInfo[] = [];
  for (const tab of tabNavigation) {
    for (const group of tab.groups) {
      collectPages(group.items, pages);
    }
  }

  // Sort by last modified (newest first)
  pages.sort((a, b) => new Date(b.lastModified).getTime() - new Date(a.lastModified).getTime());

  // Take top 50 for the feed
  const feedPages = pages.slice(0, 50);

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Future AGI Documentation</title>
    <description>Documentation for Future AGI — the AI lifecycle platform for building, evaluating, observing, and optimizing AI applications.</description>
    <link>${SITE}</link>
    <atom:link href="${SITE}/feed.xml" rel="self" type="application/rss+xml" />
    <language>en</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${feedPages.map(p => `    <item>
      <title>${escapeXml(p.title)}</title>
      <link>${SITE}${p.href}</link>
      <guid>${SITE}${p.href}</guid>
      <description>${escapeXml(p.description)}</description>
      <pubDate>${new Date(p.lastModified).toUTCString()}</pubDate>
    </item>`).join('\n')}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml; charset=utf-8',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
