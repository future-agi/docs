import type { APIRoute } from 'astro';

const siteUrl = 'https://docs.futureagi.com';

export const GET: APIRoute = () => {
  const body = `User-agent: *
Allow: /

# Sitemaps
Sitemap: ${siteUrl}/sitemap-index.xml

# LLM-friendly documentation
# See https://llmstxt.org for the specification
`;

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
