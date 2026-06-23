import type { APIRoute } from 'astro';
import { tabNavigation } from '../lib/navigation';
import type { NavItem } from '../lib/navigation';

const SITE = 'https://docs.futureagi.com';

/**
 * Generate /llms.txt — a concise, LLM-friendly overview of the documentation.
 * Follows the llms.txt specification: https://llmstxt.org
 */
export const GET: APIRoute = () => {
  const lines: string[] = [];

  // Title & summary
  lines.push('# Future AGI Documentation');
  lines.push('');
  lines.push('> Future AGI is an AI lifecycle platform for building, evaluating, observing, and optimizing AI applications. This documentation covers the Python SDK, platform features, integrations, and API reference.');
  lines.push('');

  // Key sections with links
  lines.push('## Docs');
  lines.push('');

  for (const tab of tabNavigation) {
    for (const group of tab.groups) {
      lines.push(`### ${group.group}`);
      lines.push('');
      collectLinks(group.items, lines);
      lines.push('');
    }
  }

  // Optional: pointer to full version
  lines.push('## Full Documentation');
  lines.push('');
  lines.push(`For the complete documentation with all page content, see [llms-full.txt](${SITE}/llms-full.txt).`);
  lines.push('');

  return new Response(lines.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};

function collectLinks(items: NavItem[], lines: string[]) {
  for (const item of items) {
    if (item.href) {
      lines.push(`- [${item.title}](${SITE}${item.href})`);
    }
    if (item.items) {
      collectLinks(item.items, lines);
    }
  }
}
