import type { APIRoute } from 'astro';

const siteUrl = 'https://docs.futureagi.com';

export const GET: APIRoute = () => {
  const body = `User-agent: *
Allow: /

# AI crawlers — explicitly allowed for GEO (Generative Engine Optimization)
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: GoogleOther
Allow: /

# Sitemaps & Feeds
Sitemap: ${siteUrl}/sitemap-index.xml

# RSS Feed (for Perplexity, AI crawlers, aggregators)
# ${siteUrl}/feed.xml

# LLM-friendly documentation (llmstxt.org)
# ${siteUrl}/llms.txt — index of all docs
# ${siteUrl}/llms-full.txt — full content for LLM ingestion
`;

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
