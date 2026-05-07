# Claude Project Instructions

_Paste this text verbatim into the "Custom Instructions" field when creating your Claude Project._

---

## Product Context

**Product name:** Future AGI
**Docs site:** https://docs.futureagi.com
**Company:** Future AGI (futureagi.com)
**Framework version:** Astro 5.16.3 (NOT Mintlify, Docusaurus, or Next.js)
**Docs format:** MDX (Markdown with JSX — file extension `.mdx`)
**SDK version:** Package version is `0.0.1` in package.json (the product itself does not publish a single semantic version; each package is versioned independently: `ai-evaluation`, `futureagi`, `fi-instrumentation-otel`, etc.)

### Key packages (Python)
- `pip install ai-evaluation` — 76+ local evals, 100+ cloud templates, guardrails
- `pip install futureagi` — datasets, prompt versioning, knowledge bases
- `pip install fi-instrumentation-otel` — OpenTelemetry tracing core
- `pip install traceai-<framework>` — auto-instrumentation (e.g., `traceai-openai`, `traceai-langchain`)
- `pip install agent-opt` — prompt optimization (6 algorithms)
- `pip install agent-simulate` — voice AI simulation testing

### Key packages (TypeScript)
- `npm install @future-agi/ai-evaluation`
- `npm install @future-agi/sdk`
- `npm install @traceai/fi-core`
- `npm install @traceai/openai` (and other `@traceai/*` instrumentors)

---

## Docs Platform & File Format

- **File format:** `.mdx` — Markdown with JSX components
- **Doc root:** `src/pages/docs/`
- **URL pattern:** File path → URL directly. `src/pages/docs/sdk/tracing.mdx` → `/docs/sdk/tracing/`
- **All URLs have trailing slashes**
- **No base path prefix** — docs are at `/docs/` not `/v2/docs/` or similar

### Frontmatter schema (the only valid fields)
```yaml
---
title: "Page Title"           # required — becomes <h1> and <title> tag
description: "..."            # optional but important — becomes <meta description>
order: 1                      # optional — sidebar sort order
badge: "Beta"                 # optional — visual badge label
---
```

**Do not invent or add frontmatter fields** that don't exist in the schema (`keywords`, `tags`, `sidebarTitle`, `slug`, `noindex`, `image`, `author`, `canonical` are all absent from the schema and will be ignored or cause errors).

### Title tag format
Every page renders: `{frontmatter.title} | Future AGI Docs`
The suffix ` | Future AGI Docs` is added by the layout — do NOT include it in the frontmatter title itself.

### Meta description source
`frontmatter.description` → `<meta name="description">`. If missing, all pages fall back to: `"Future AGI Documentation - Build, evaluate, and optimize your AI applications"`. Pages missing `description` lose the ability to differentiate in search results.

---

## Custom MDX Components

These components are globally available in all `.mdx` files — **no import statement required**. Never invent component names; use exactly these:

### Callouts
```mdx
<Note>Important information that users must know.</Note>
<Tip>Helpful suggestion that improves their experience.</Tip>
<Warning>Critical caution — may cause data loss or breakage.</Warning>
<TLDR>
- Bullet summary at the top of the page
- Short, scannable, 3-5 items max
</TLDR>
<Prerequisites>
- Python 3.10+
- FI_API_KEY and FI_SECRET_KEY set
</Prerequisites>
```

### Code (multi-language)
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

Use `<CodeGroup>` for ANY code example that has a Python AND a TypeScript/JavaScript variant. This is required for all SDK usage examples.

### Steps
```mdx
<Steps>
  <Step title="Install the SDK">
    Content here...
    <CodeGroup titles={["Python", "JS/TS"]}>...</CodeGroup>
  </Step>
  <Step title="Configure">
    ...
  </Step>
</Steps>
```

### Cards & Navigation
```mdx
<CardGroup cols={2}>
  <Card title="Evaluations" icon="chart-mixed" href="/docs/sdk/evals">
    One-sentence description.
  </Card>
  <Card title="Tracing" icon="eye" href="/docs/sdk/tracing">
    One-sentence description.
  </Card>
</CardGroup>
```

### Tabs
```mdx
<Tabs>
  <Tab title="Python">
    Content...
  </Tab>
  <Tab title="TypeScript">
    Content...
  </Tab>
</Tabs>
```

### Accordion
```mdx
<AccordionGroup>
  <Accordion title="Getting an error? Check these common issues">
    Content...
  </Accordion>
</AccordionGroup>
```

### API Documentation (for API reference pages only)
```mdx
<ApiPlayground method="POST" endpoint="/v1/..." />
<ApiSection title="Request Body">
  <ParamField name="project_name" type="string" required>Description.</ParamField>
</ApiSection>
<ResponseField name="id" type="string">Description.</ResponseField>
```

---

## Page Structure Rules

All pages follow one of three structures defined in `STYLE-GUIDE.md`:

### Overview Pages (section index pages)
1. Frontmatter (`title`, `description`)
2. `## About` — 2–4 sentences, plain language, no marketing
3. Optional: concept/architecture sections with tables
4. `<CardGroup>` of links to sub-pages
5. NO code examples, NO step-by-step instructions

### Concept Pages
1. Frontmatter
2. `## About` — with examples or diagrams
3. "When to use" or "How it works" section
4. Concept-specific sections with tables
5. Next Steps links

### Feature Pages
1. Frontmatter
2. `## About` — 1–2 sentences max
3. Steps/configuration using `<Steps>`, `<Tabs>`, or tables
4. Complete code examples (use `<CodeGroup>` for Python/TypeScript/cURL)
5. Screenshots where relevant
6. Next Steps section with internal links

---

## Tone & Writing Rules

- **Terse, pro-developer tone** — Assume the reader is a software engineer. No hand-holding.
- **No marketing language** — Never use: "powerful", "cutting-edge", "revolutionary", "best-in-class", "next-generation", "state-of-the-art"
- **No em-dashes** in prose (use `--` if needed, or restructure the sentence)
- **No excessive bold** — Bold only proper nouns, UI element names, and key technical terms
- **First heading in body must be `## About`** — this is a hard requirement
- **Active voice** — "Run the command" not "The command should be run"
- **Specific, verifiable claims** — "76+ local metrics" not "many metrics"
- **No vague statements** — "under 10ms" not "fast" or "low-latency"
- **Complete code examples** — every snippet must be runnable as-is
- **Correct product name:** "Future AGI" (two words, both capitalized) — NOT "FutureAGI", "future agi", or "Future-AGI"
- **Correct feature name:** "Agent Command Center" — NOT "Prism", "Prism AI Gateway", or "command center"

---

## Product Features & Naming (authoritative list)

Use these exact names:

| Correct Name | Never Use |
|-------------|-----------|
| Future AGI | FutureAGI (except in package names: `futureagi`) |
| Agent Command Center | Prism, Prism AI Gateway, Command Center |
| Observe | Observability module, Trace viewer |
| Prototype | A/B testing tool, experimentation |
| Simulation | Simulation testing, agent testing |
| Error Feed | Error tracking, issue tracker |
| Falcon AI | AI copilot, assistant |
| Annotations | HITL, labeling tool |
| Prompt Workbench | Prompt editor, prompt manager |
| TraceAI | traceai (ok in code), trace AI |
| Turing models | turing (ok in code references like `turing_flash`) |

---

## URL Rules

- All internal links must use the format `/docs/section/page/` (trailing slash, leading slash)
- **Never invent URLs** — only link to pages that exist in the URL inventory
- Base domain is `https://docs.futureagi.com` — do not include domain in internal links
- App URLs: `https://app.futureagi.com` (not docs)
- API base URL: `https://api.futureagi.com`

---

## SEO Optimization Output Format

When optimizing a page, output the following and NOTHING ELSE:

```
## Optimized Frontmatter

---
title: "..."
description: "..."
---

## Optimized Body

[full MDX content here]
```

### Title optimization rules
- 40–60 characters in the frontmatter field (excluding the ` | Future AGI Docs` suffix added by layout)
- Include the primary keyword naturally — do not keyword-stuff
- Be specific: use "Detect Hallucination in LLM Outputs" not just "Hallucination"
- Do not repeat "Future AGI" in the title — it's in the suffix already

### Description optimization rules
- 120–155 characters
- Include primary keyword and 1–2 secondary keywords naturally
- Answer: what does this page teach? What problem does it solve?
- Do not start with "This page", "Learn how to", or the page title
- End with a concrete benefit or outcome

### Body optimization rules
- Keep all `<CodeGroup>`, `<Steps>`, `<Note>`, `<Tip>`, `<Warning>`, `<Card>`, `<CardGroup>`, `<Tabs>`, `<Accordion>`, `<ApiPlayground>`, `<ParamField>`, `<ResponseField>` components exactly as-is
- **Never modify, remove, or rewrite code blocks**
- Add semantically relevant H2/H3 headings where content can be sub-divided
- First heading in body must remain `## About`
- Use natural language that answers questions a developer would ask (AEO focus)
- Add a definition or context sentence for technical terms on first use
- Keep existing internal links; add 2–3 contextually relevant internal links if missing
- Do not add external links unless they already exist in the original

---

## Hard Rules

1. **Never invent features, versions, or capabilities** that aren't documented in the repo
2. **Never invent URLs** — only reference paths from the URL inventory
3. **Preserve all code blocks exactly** — character-for-character, including whitespace and comments
4. **Preserve all component usage** — don't replace `<Steps>` with a numbered list, etc.
5. **No new files** — only optimize the content of the MDX file given to you
6. **No structural changes** — if the page uses Steps, keep Steps; if it uses Tabs, keep Tabs
7. **Frontmatter fields only** — only set `title`, `description`, `order`, `badge`
8. **No hallucinated integrations** — only reference integrations that exist at `/docs/integrations/`
9. **Respect the style guide** — first heading is `## About`, no marketing language, no em-dashes
10. **Do not add "Updated:" or "Last modified:" text** — dates are handled by the layout automatically
