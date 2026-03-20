import type { APIRoute } from 'astro';
import { tabNavigation } from '../lib/navigation';

interface SearchEntry { title: string; href: string; group: string; tab: string; }

function flattenItems(items: any[], group: string, tab: string, out: SearchEntry[]) {
  for (const item of items) {
    if (item.href) out.push({ title: item.title, href: item.href, group, tab });
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
