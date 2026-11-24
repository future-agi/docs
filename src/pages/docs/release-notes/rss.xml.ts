import type { APIRoute } from 'astro';
import fs from 'node:fs/promises';
import path from 'node:path';

const SITE = 'https://docs.futureagi.com';
const PAGE = '/docs/release-notes';
const SOURCE = path.join(process.cwd(), 'src/pages/docs/release-notes.mdx');
const MAX_ITEMS = 30;

/**
 * Generate /docs/release-notes/rss.xml: one item per dated "## " section of the
 * release-notes page ("## Week of 2026-11-16", "## 1.59.0 (2026-11-18)", ...),
 * newest date first. Feed readers and the Slack RSS app (`/feed subscribe <url>`)
 * post each new section as it is published.
 */

interface Section {
  heading: string;
  date: string;
  body: string;
}

function parseSections(source: string): Section[] {
  const out: Section[] = [];
  const heading = /^## (.+?)\s*$/gm;
  const matches = [...source.matchAll(heading)];
  matches.forEach((m, i) => {
    const date = m[1].match(/\d{4}-\d{2}-\d{2}/)?.[0];
    if (!date) return;
    const start = (m.index ?? 0) + m[0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index : source.length;
    out.push({ heading: m[1], date, body: source.slice(start, end) });
  });
  // Newest first by date, whatever order the sections were merged in.
  return out.sort((a, b) => b.date.localeCompare(a.date));
}

/** Same ids the page renders for its headings (github-slugger rules). */
function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s_-]/gu, '')
    .replace(/\s/g, '-');
}

/** Escape for HTML, leaving entities the MDX source already wrote (`&lt;`) alone. */
function escapeHtml(s: string): string {
  return s.replace(/&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeXml(s: string): string {
  return escapeHtml(s).replace(/"/g, '&quot;');
}

function absolute(href: string): string {
  if (href.startsWith('#')) return `${SITE}${PAGE}${href}`;
  if (href.startsWith('/')) return `${SITE}${href}`;
  return href;
}

/** Inline markdown (code, bold, links) to HTML. Code spans are set aside first so their contents stay literal. */
function inline(md: string): string {
  const codes: string[] = [];
  let s = md
    .replace(/\\([{}<>*_`[\]])/g, '$1') // MDX escapes like \{ and \<
    .replace(/`([^`]+)`/g, (_m, code) => {
      codes.push(code);
      return `\u0000${codes.length - 1}\u0000`;
    });
  s = escapeHtml(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/g, (_m, text, href) => `<a href="${escapeXml(absolute(href))}">${text}</a>`);
  return s.replace(/\u0000(\d+)\u0000/g, (_m, i) => `<code>${escapeHtml(codes[Number(i)])}</code>`);
}

/** Turn one section's MDX into simple HTML: subsection headings, bullet lists, and paragraphs. */
function sectionToHtml(body: string): string {
  const out: string[] = [];
  let list = false;
  let buf: string[] = [];
  let kind: 'li' | 'p' | null = null;

  const flush = () => {
    if (buf.length && kind) out.push(`<${kind}>${inline(buf.join(' '))}</${kind}>`);
    buf = [];
    kind = null;
  };
  const closeList = () => {
    flush();
    if (list) out.push('</ul>');
    list = false;
  };

  const text = body.replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const subsection = line.match(/^<div[^>]*>([^<]+)<\/div>$/) || line.match(/^#{3,6}\s+(.+)$/);
    if (subsection) {
      closeList();
      out.push(`<h3>${inline(subsection[1].trim())}</h3>`);
    } else if (line.startsWith('<')) {
      // Wrapper divs, images, and MDX components are layout, not prose.
      closeList();
    } else if (/^[-*] /.test(line)) {
      flush();
      if (!list) out.push('<ul>');
      list = true;
      kind = 'li';
      buf.push(line.slice(2));
    } else if (line === '') {
      flush();
    } else if (kind) {
      buf.push(line);
    } else {
      closeList();
      kind = 'p';
      buf.push(line);
    }
  }
  closeList();
  return out.join('\n');
}

function rfc822(date: string): string {
  return new Date(`${date}T00:00:00Z`).toUTCString();
}

export const GET: APIRoute = async () => {
  const source = await fs.readFile(SOURCE, 'utf-8');
  const sections = parseSections(source).slice(0, MAX_ITEMS);

  const items = sections
    .map((s) => {
      const url = `${SITE}${PAGE}#${slug(s.heading)}`;
      return `    <item>
      <title>${escapeXml(s.heading)}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <pubDate>${rfc822(s.date)}</pubDate>
      <description><![CDATA[${sectionToHtml(s.body).replace(/]]>/g, ']]&gt;')}]]></description>
    </item>`;
    })
    .join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Future AGI Release Notes</title>
    <link>${SITE}${PAGE}</link>
    <description>Weekly technical release notes for the Future AGI platform: features, improvements, fixes, and breaking changes.</description>
    <atom:link href="${SITE}${PAGE}/rss.xml" rel="self" type="application/rss+xml" />
    <language>en</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
${items}
  </channel>
</rss>
`;

  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
};
