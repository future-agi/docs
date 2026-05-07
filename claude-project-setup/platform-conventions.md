# Platform Conventions

## Docs Platform

- **Framework:** Astro 5.16.3 (static site generation)
- **Content format:** `.mdx` (Markdown with JSX — all doc pages)
- **Site URL:** `https://docs.futureagi.com`
- **Package name:** `bustling-binary` (internal, version `0.0.1`)
- **No Mintlify, Docusaurus, or GitBook** — pure Astro

### Key dependencies (from `package.json`)
| Package | Version | Purpose |
|---------|---------|---------|
| `astro` | ^5.16.3 | Framework |
| `@astrojs/mdx` | ^4.3.12 | MDX support |
| `@astrojs/react` | ^4.3.1 | React for interactive components |
| `@astrojs/sitemap` | ^3.6.0 | Auto sitemap generation |
| `tailwindcss` | ^4.1.17 | Styling |
| `shiki` | ^3.18.0 | Syntax highlighting |
| `pagefind` | ^1.4.0 | Static full-text search |
| `fuse.js` | ^7.1.0 | Fuzzy search |
| `@giscus/react` | ^3.1.0 | Comments |

---

## File Format and Location

- All documentation pages are **`.mdx`** files
- Located under `src/pages/docs/` (605 files total)
- Root-level special pages: `src/pages/docs/faq.mdx`, `installation.mdx`, `release-notes.mdx`, `roles-and-permissions.mdx`, `self-hosting.mdx`
- Homepage: `src/pages/index.astro` (Astro component, not MDX)
- Changelog: `src/pages/changelog.mdx`

---

## Frontmatter Schema

Defined in `src/content/config.ts` using Astro content collections with Zod:

```typescript
const docs = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),           // required
    description: z.string().optional(),
    order: z.number().optional(),
    badge: z.string().optional(),
  }),
});
```

### Field usage across the site

| Field | Required | Observed frequency | Notes |
|-------|----------|-------------------|-------|
| `title` | Yes | 100% of pages | Used as H1 and `<title>` tag |
| `description` | No | ~80% of pages (estimated) | Used as `<meta name="description">` |
| `order` | No | Rare — sidebar sort order | Not widely used in sampled pages |
| `badge` | No | Rare — "Beta", "Deprecated" indicators | Not widely used in sampled pages |

### Example frontmatter (typical page)
```yaml
---
title: "Setup Observability"
description: "Set up Future AGI Observe for production monitoring. Configure auto-instrumented tracing for OpenAI, Anthropic, LangChain, and other LLM frameworks."
---
```

### Example frontmatter (minimal — only required field)
```yaml
---
title: "Overview"
---
```

**Note:** No `layout`, `sidebarTitle`, `slug`, `tags`, `keywords`, `noindex`, `canonical`, or `image` fields are in the schema. Those SEO fields do not currently exist at the page level.

---

## Routing Rules

Astro file-based routing — file path maps directly to URL:

| File path | URL |
|-----------|-----|
| `src/pages/docs/index.mdx` | `/docs/` |
| `src/pages/docs/sdk/index.mdx` | `/docs/sdk/` |
| `src/pages/docs/sdk/tracing.mdx` | `/docs/sdk/tracing/` |
| `src/pages/docs/evaluation/builtin/toxicity.mdx` | `/docs/evaluation/builtin/toxicity/` |

- All URLs get a trailing slash
- No base path prefix beyond `/docs/` for documentation
- No custom slug overrides (file name = URL slug)

---

## Anchor ID Behavior

- Auto-generated from heading text by Astro/MDX
- Heading `## My Feature Name` → anchor `#my-feature-name` (lowercase, spaces → hyphens)
- No manual anchor ID syntax in current use
- Table of Contents component (`src/components/TableOfContents.astro`) reads the `headings` prop passed from the layout

---

## Custom MDX Components

All 32 components live in `src/components/docs/`. Import in individual pages is **not required** — components are globally available via Astro's MDX configuration.

### Content Callouts

| Component | Usage | Example |
|-----------|-------|---------|
| `<Note>` | Informational callout | `<Note>This requires Python 3.10+.</Note>` |
| `<Tip>` | Helpful suggestion | `<Tip>You don't need to install dependencies manually.</Tip>` |
| `<Warning>` | Important caution | `<Warning>Deleting a queue is irreversible.</Warning>` |
| `<Callout>` | Generic callout (type prop: info/success/warning/error) | `<Callout type="info">...</Callout>` |
| `<TLDR>` | Summary block at top of page | `<TLDR>- Python: evals, tracing\n- TypeScript: evals</TLDR>` |
| `<Check>` | Checkmark icon inline | `<Check /> Passed` |
| `<Update>` | Changelog entry / release note callout | `<Update>Added in v2.1</Update>` |
| `<Tooltip>` | Inline tooltip on hover | `<Tooltip tip="Hover text">Term</Tooltip>` |
| `<Prerequisites>` | Prerequisites block before steps | `<Prerequisites>...</Prerequisites>` |

### Code Blocks

| Component | Usage | Example |
|-----------|-------|---------|
| `<CodeGroup titles={["Python","JS/TS"]}>` | Tabbed multi-language code block | Wraps multiple ` ```lang ``` ` fences |
| `<CodeBlock>` | Single code block with syntax highlighting | `<CodeBlock lang="python">...</CodeBlock>` |
| `<CodePanel>` | Individual panel inside CodeGroup | Used internally by CodeGroup |

**Standard pattern for multi-language examples:**
```mdx
<CodeGroup titles={["Python", "JS/TS"]}>
```python Python
pip install ai-evaluation
```
```bash JS/TS
npm install @future-agi/ai-evaluation
```
</CodeGroup>
```

### Navigation & Layout

| Component | Usage | Example |
|-----------|-------|---------|
| `<Card title="..." icon="..." href="...">` | Linked card with icon | Navigation cards at bottom of overview pages |
| `<CardGroup cols={2}>` | Grid of cards (cols: 2, 3, or 4) | `<CardGroup cols={2}><Card .../><Card .../></CardGroup>` |
| `<CardGrid>` | Alternative card grid | Less common than CardGroup |
| `<Tabs>` | Tab group container | `<Tabs><Tab title="Python">...</Tab></Tabs>` |
| `<Tab title="...">` | Individual tab | Inside `<Tabs>` |
| `<TabPanel>` | Tab content panel | Used internally |
| `<Accordion title="...">` | Collapsible section | `<Accordion title="Common errors">...</Accordion>` |
| `<AccordionGroup>` | Wrapper for multiple accordions | `<AccordionGroup>...</AccordionGroup>` |
| `<Expandable>` | Expandable content block | Less common alternative to Accordion |

### Step-by-Step Guides

| Component | Usage |
|-----------|-------|
| `<Steps>` | Container for numbered steps |
| `<Step title="...">` | Individual step — auto-numbered by CSS counter |

**Standard pattern:**
```mdx
<Steps>
  <Step title="Install the SDK">
    Content here...
    <CodeGroup titles={["Python", "JS/TS"]}>...
    </CodeGroup>
  </Step>
  <Step title="Configure">
    ...
  </Step>
</Steps>
```

### API Documentation

| Component | Props | Purpose |
|-----------|-------|---------|
| `<ApiPlayground>` | method, endpoint, baseUrl, parameters, requestBody, responseExample, responseStatus | Interactive API explorer with code generation (cURL, Python, JS, SDK) |
| `<ApiSection>` | title | Groups request/response fields |
| `<ApiEndpoint>` | method, path | Displays endpoint badge |
| `<ApiCollapsible>` | — | Collapsible API response fields |
| `<ApiExplorer>` | — | Full interactive API explorer |
| `<ParamField>` | name, type, required | Documents request parameter |
| `<ResponseField>` | name, type | Documents response field |

**Standard API page pattern:**
```mdx
<ApiPlayground
  method="POST"
  endpoint="/v1/agent-definitions"
  baseUrl="https://api.futureagi.com"
  parameters={[...]}
  requestBody={{...}}
  responseExample={{...}}
  responseStatus={201}
/>
```

### Utility Components

| Component | Purpose |
|-----------|---------|
| `<Icon name="...">` | SVG icon from Heroicons set |
| `<CopyButton>` | Copy-to-clipboard button |

---

## Meta Tag Setup

Meta tags are generated in **two layouts** — not in frontmatter directly.

### `src/layouts/BaseLayout.astro`
Generates all SEO/social tags from `title` and `description` props:

```html
<title>{title} | Future AGI Docs</title>
<meta name="description" content={description} />
<link rel="canonical" href={canonicalURL.href} />

<!-- Open Graph -->
<meta property="og:title" content={title} />
<meta property="og:description" content={description} />
<meta property="og:type" content="website" />
<meta property="og:url" content={canonicalURL.href} />
<meta property="og:image" content="https://docs.futureagi.com/og-image.png" />
<meta property="og:site_name" content="Future AGI Docs" />

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content={title} />
<meta name="twitter:description" content={description} />
<meta name="twitter:image" content="https://docs.futureagi.com/og-image.png" />
```

Also generates `TechArticle` JSON-LD with `dateModified` from file system mtime.

### `src/layouts/DocsLayout.astro`
Wraps `BaseLayout`, passes `frontmatter.title` and `frontmatter.description`.
Also generates **BreadcrumbList JSON-LD** per page.

**Title format:** `{frontmatter.title} | Future AGI Docs`

**Default description** (when frontmatter `description` is missing):
`"Future AGI Documentation - Build, evaluate, and optimize your AI applications"`

---

## Structured Data (JSON-LD)

Two schema types are emitted on every docs page:

### 1. TechArticle (from BaseLayout)
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

### 2. BreadcrumbList (from DocsLayout)
```json
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    { "@type": "ListItem", "position": 1, "name": "Docs", "item": "https://docs.futureagi.com/docs" },
    { "@type": "ListItem", "position": 2, "name": "SDK", "item": "https://docs.futureagi.com/docs/sdk" },
    { "@type": "ListItem", "position": 3, "name": "SDKs", "item": "https://docs.futureagi.com/docs/sdk/" }
  ]
}
```

---

## Sitemap

- **Location:** `sitemap.xml` at repo root (committed artifact)
- **Generator:** `@astrojs/sitemap` integration — auto-generated during `pnpm build`
- **Sitemap index:** `sitemap-index.xml` (referenced in robots.txt)
- **Format:** Standard XML Sitemap Protocol
- **No `<lastmod>` or `<priority>` tags** in current entries
- **Count:** 484 URLs in current committed sitemap

---

## robots.txt

Dynamically generated from `src/pages/robots.txt.ts`:

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

AI crawlers are **explicitly allowed** — this is intentional GEO (Generative Engine Optimization) configuration.

---

## Additional Special Files

| File | URL | Purpose |
|------|-----|---------|
| `src/pages/llms.txt.ts` | `/llms.txt` | LLM-friendly plain-text doc index |
| `src/pages/llms-full.txt.ts` | `/llms-full.txt` | Full content for LLM indexing |
| `src/pages/feed.xml.ts` | `/feed.xml` | RSS feed for aggregators and AI crawlers |
| `src/pages/search-data.json.ts` | `/search-data.json` | Pagefind search index |
| `src/pages/robots.txt.ts` | `/robots.txt` | Dynamic robots file |

---

## Style Guide Summary

From `STYLE-GUIDE.md` in repo root — three page types:

### Overview Pages
- `## About` heading first (plain language, no marketing)
- Optional concept sections
- Cross-links to related features
- Getting Started `<CardGroup>` at bottom
- No code examples, no UI screenshots

### Concept Pages
- `## About` with examples or diagrams
- "When to use" section
- Concept-specific sections with tables
- No step-by-step instructions

### Feature Pages
- `## About` (1–2 sentences max)
- Steps/configuration using `<Steps>`, `<Tabs>`, or tables
- Code examples (required for SDK usage — use `<CodeGroup>` for Python/TypeScript/cURL)
- Screenshots where relevant
- Next Steps links at bottom

### Writing Rules (from STYLE-GUIDE.md)
- First heading must be `## About`
- No em-dashes in prose
- No excessive bold or marketing language
- Specific, verifiable claims only
- All internal links must resolve
- Code examples must be complete and copy-pasteable
- Use `<Note>`, `<Tip>`, `<Warning>` sparingly — one per logical section at most
