# Existing SEO Audit

Site: `https://docs.futureagi.com`
Audit date: 2026-05-05
Pages audited: 605

---

## Title Tags

### How titles are generated
- **Template:** `{frontmatter.title} | Future AGI Docs`
- Set in `src/layouts/BaseLayout.astro` line 65: `<title>{title}</title>`
- Title value is `frontmatter.title` + literal ` | Future AGI Docs` (appended by DocsLayout)
- There is no per-page override mechanism — if `frontmatter.title` is set, that's what you get

### Title length analysis
Average frontmatter title: **~20–35 characters** before the suffix.
Full rendered `<title>` with suffix adds 16 characters (` | Future AGI Docs`).

| Title fragment (frontmatter) | Full `<title>` tag | Chars |
|---|---|---|
| `"Setup Observability"` | `Setup Observability \| Future AGI Docs` | 37 |
| `"SDKs"` | `SDKs \| Future AGI Docs` | 22 |
| `"Overview"` | `Overview \| Future AGI Docs` | 25 |
| `"Annotations"` | `Annotations \| Future AGI Docs` | 29 |
| `"GEPA: Evolutionary Prompt Optimization"` | `GEPA: Evolutionary Prompt Optimization \| Future AGI Docs` | 56 |
| `"Customer Agent Conversation Quality"` | `Customer Agent Conversation Quality \| Future AGI Docs` | 54 |

**Issues found:**
- Many section **index pages use generic titles** like `"Overview"` — the full title becomes `Overview | Future AGI Docs` with no product context. At least 15+ pages have this issue (agent-playground/index, dataset/index, observe/index, optimization/index, prototype/index, simulation/index, prompt/index, etc.)
- The title `"Quickstart"` appears on multiple pages (annotations quickstart, command-center quickstart, etc.) — these produce **duplicate title tags**
- Some titles are **too short**: `"SDKs"`, `"Overview"`, `"FAQs"` — underusing the ~60 character budget
- Some titles may approach 70+ characters when suffix is added: `"GEPA: Evolutionary Prompt Optimization | Future AGI Docs"` = 56 chars (acceptable but close for longer ones)
- **No keyword-optimized titles** found — titles describe function, not search intent

### Duplicate titles (confirmed)
| Title | Affected pages |
|-------|----------------|
| `Overview \| Future AGI Docs` | agent-playground, dataset, observe, optimization, prompt, prototype, simulation, knowledge-base, and others |
| `Quickstart \| Future AGI Docs` | annotations/quickstart, command-center/quickstart, and potentially others |

---

## Meta Descriptions

### How descriptions are generated
- Source: `frontmatter.description` field (optional)
- Set in `src/layouts/BaseLayout.astro` line 24: `<meta name="description" content={description} />`
- **Default fallback** (when description is missing): `"Future AGI Documentation - Build, evaluate, and optimize your AI applications"`
- No per-section defaults — all missing descriptions get the same global fallback

### Coverage
From sampling ~30 pages across sections, description coverage is approximately:
- Pages **with** `description`: ~80% (estimated — most sampled pages had one)
- Pages **without** `description`: ~20% (notably `roles-and-permissions.mdx` confirmed missing; likely others in the built-in evals section and API endpoints section)

### Description length analysis
| Page | Description | Chars |
|------|-------------|-------|
| /docs/quickstart/setup-observability/ | "Set up Future AGI Observe for production monitoring. Configure auto-instrumented tracing for OpenAI, Anthropic, LangChain, and other LLM frameworks." | 149 |
| /docs/sdk/ | "Evaluate LLM outputs, trace AI calls, optimize prompts, and test voice agents. Python, TypeScript, Java, and C# supported." | 121 |
| /docs/evaluation/ | "Measure and compare quality of prompts and agents across datasets, simulations, and experiments." | 96 |
| /docs/annotations/ | "Add human feedback to your AI outputs with annotation labels, queues, and scores across traces, datasets, prototypes, and simulations." | 132 |
| /docs/observe/ | "Monitor and evaluate LLM applications in production with real-time tracing, session analysis, and alerting." | 107 |
| /docs/admin-settings/ | "Manage your account, organization, workspaces, API keys, integrations, billing, and team." | 89 |

Average length (sampled): **~100–130 characters** — within acceptable range but several could be more specific.

**Issues found:**
- Pages missing description get the **same generic fallback** — search results for all missing pages show identical snippet text
- `roles-and-permissions.mdx` confirmed missing description
- The 80+ **built-in eval pages** (toxicity, bias-detection, groundedness, etc.) likely have thin or auto-patterned descriptions — TODO: audit individually
- The 177 **API reference pages** likely have auto-generated descriptions following a formula — not differentiated for search

### Confirmed missing descriptions
- `/docs/roles-and-permissions/` — no `description` field in frontmatter (confirmed)
- TODO: Audit all 80 built-in eval pages individually
- TODO: Audit all API endpoint pages individually

---

## Structured Data (JSON-LD)

### TechArticle (all pages)
Emitted by `src/layouts/BaseLayout.astro`:
```json
{
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "headline": "<page title>",
  "description": "<meta description>",
  "url": "<canonical URL>",
  "inLanguage": "en",
  "dateModified": "<file mtime ISO 8601>",
  "publisher": {
    "@type": "Organization",
    "name": "Future AGI",
    "url": "https://futureagi.com",
    "logo": { "@type": "ImageObject", "url": "https://docs.futureagi.com/og-image.png" }
  },
  "isPartOf": {
    "@type": "WebSite",
    "name": "Future AGI Documentation",
    "url": "https://docs.futureagi.com",
    "potentialAction": { "@type": "SearchAction", ... }
  }
}
```

**Present on:** All pages via BaseLayout
**`dateModified`:** Derived from `fs.statSync(filePath).mtime.toISOString()` — actual file modification time from the build server filesystem (not from git history — may reflect deployment timestamps, not authorship dates)

### BreadcrumbList (all docs pages)
Emitted by `src/layouts/DocsLayout.astro`:
- Auto-generated from URL path segments
- Segments converted: `hyphens → spaces → Title Case`
- Last segment overridden with `frontmatter.title`
- Only links to breadcrumb items that have actual pages (checks filesystem)

**Present on:** All pages using DocsLayout (all `/docs/*` pages)

### Missing schema types
- No `FAQPage` schema on `/docs/faq/`
- No `HowTo` schema on quickstart/step-by-step pages
- No `SoftwareApplication` schema for the product itself
- No `APIReference` type for API endpoint pages

---

## Canonical Tags

- **Set by:** `src/layouts/BaseLayout.astro` line 31
- **Format:** `<link rel="canonical" href={canonicalURL.href} />`
- **Value:** `new URL(Astro.url.pathname, Astro.site)` — automatically constructed from the current page URL and `site: 'https://docs.futureagi.com'` in `astro.config.mjs`
- **Trailing slash:** All URLs end with `/` — canonical matches actual URL format
- **Coverage:** 100% of pages (canonical is always set)
- **Issues:** None confirmed — canonicals look correct. However, if `prism/*` redirects point to `command-center/*`, verify canonical on redirect target is `command-center/*` not `prism/*`

---

## Open Graph Tags

Set in `src/layouts/BaseLayout.astro`:
```html
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{description}" />
<meta property="og:type" content="website" />
<meta property="og:url" content="{canonical URL}" />
<meta property="og:image" content="https://docs.futureagi.com/og-image.png" />
<meta property="og:site_name" content="Future AGI Docs" />
```

**Issues:**
- `og:image` is a **single static image** for all 605 pages — no per-page OG images
- `og:type` is `"website"` for all pages — should be `"article"` for content pages
- `og:title` inherits the full `{title} | Future AGI Docs` format — same duplicate-title issues apply

---

## Twitter Card Tags

```html
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{title}" />
<meta name="twitter:description" content="{description}" />
<meta name="twitter:image" content="https://docs.futureagi.com/og-image.png" />
```

**Present on:** All pages
**Issues:** Same as OG — static image, no per-page customization. No `twitter:site` or `twitter:creator` tags set.

---

## Sitemap

- **File:** `/sitemap.xml` (committed to repo root)
- **Generator:** `@astrojs/sitemap` auto-generates during build
- **Sitemap index:** `https://docs.futureagi.com/sitemap-index.xml` (referenced in robots.txt)
- **URL count (committed file):** 484 URLs
- **Actual page count:** 605 files

**Missing from committed sitemap (~120 URLs unaccounted for):**
- The sitemap appears to be from a prior build. Notably, the sitemap contains **`/docs/prism/*`** URLs (16 entries) but **no `/docs/command-center/*`** URLs — this is the opposite of what you want if prism redirects to command-center.
- TODO: Verify which pages are excluded from sitemap generation (Astro sitemap excludes redirect-only routes by default)
- TODO: After next build, confirm sitemap contains command-center URLs and excludes prism URLs (since prism pages are 301 redirects)

**`<lastmod>` tags:** Not present in committed sitemap — all URLs have no modification date
**`<priority>` tags:** Not present — all pages treated equally
**`<changefreq>` tags:** Not present

---

## robots.txt

Generated dynamically from `src/pages/robots.txt.ts`:
```
User-agent: *
Allow: /

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

Sitemap: https://docs.futureagi.com/sitemap-index.xml
```

**Assessment:** Well-configured. Explicitly allows AI crawlers — good for GEO. References sitemap-index.xml correctly. No pages are disallowed.

---

## `lastmod` / `updated` Date Handling

- **Per-page:** `dateModified` in `TechArticle` JSON-LD comes from `fs.statSync(filePath).mtime` — filesystem modification time at build time
- **Sitemap:** No `<lastmod>` tags in the current committed sitemap
- **In-page display:** No visible "last updated" date shown to users
- **Risk:** `mtime` from build server may not reflect true content authorship dates — a file touched during CI will get the CI timestamp, not the author's edit date

---

## Pages Missing H1

In Astro MDX docs, the H1 is rendered from `frontmatter.title` by the DocsLayout (not written as `# Title` in the MDX body). The layout outputs the title as an `<h1>` element in the article header.

**Result:** All pages using DocsLayout have an H1 rendered from the layout. Pages would only be missing an H1 if they used a custom layout that doesn't output the title — no such pages found in sampling.

**However:** Several pages open with `## About` as the first heading in body content, which is correct per the style guide.

TODO: Verify that index.astro (homepage) has an H1 — it uses a different layout.

---

## Duplicate H1s Across the Site

Multiple pages share the same `frontmatter.title` value, which means identical H1 text across different URLs:

| H1 text | Affected pages (estimated) |
|---------|---------------------------|
| `Overview` | 10+ section index pages |
| `Quickstart` | 4+ pages across different sections |
| `Concepts` | Unknown — possible |

This is a significant SEO issue: search engines may have difficulty differentiating pages with identical H1s at different URLs.

---

## Pages With No Internal Outgoing Links

From the style guide, all feature pages should have a "Next Steps" section with internal links. Overview pages should link to feature pages via CardGroup.

**Likely candidates for no outgoing links:**
- Built-in evaluation pages (80 pages in `/docs/evaluation/builtin/`) — these may be short reference pages with no links to other sections
- API endpoint pages — these may describe a single endpoint with no navigation links
- TODO: Systematic audit needed — run `scripts/audit-links.mjs` and check for pages with zero internal `href` attributes

---

## Other SEO Issues

1. **Missing `<html lang="en">` alternate tags** — no `hreflang` (single-language site, so not critical)
2. **No RSS/Atom autodiscovery for main content** — `/feed.xml` exists but may not cover all pages
3. **`og:type` should be `article` not `website`** for doc pages
4. **No `author` meta tag** anywhere
5. **No `keywords` meta tag** (not critical for modern SEO but worth noting for AEO)
6. **Static OG image** for all 605 pages — missed opportunity for per-page visual differentiation
7. **`datePublished` missing** from JSON-LD `TechArticle` — only `dateModified` present
8. **No FAQ schema** on the `/docs/faq/` page
9. **API endpoint pages** lack `APIReference` or `TechArticle` schema fields that map to their endpoint structure
10. **Bing Webmaster Tools** verification meta tag is present (`msvalidate.01`) but **no Google Search Console** verification meta tag found
