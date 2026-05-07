# SEO / AEO / GEO Optimization Setup

This folder contains everything you need to set up a Claude Project for optimizing 605 documentation pages on https://docs.futureagi.com.

---

## Step 1: Create the Claude Project

1. Go to https://claude.ai and sign in
2. Click **Projects** in the left sidebar
3. Click **New Project**
4. Name it: `Future AGI Docs SEO`
5. (Optional) Add a brief description: `Optimize 605 MDX docs pages for SEO, AEO, and GEO`

---

## Step 2: Paste the Custom Instructions

1. Inside the project, click **Edit project details** (or the settings gear)
2. Find the **Custom instructions** field
3. Open `claude-project-setup/project-instructions.md` and copy **everything after the `---` separator at the top**
4. Paste it into the Custom Instructions field
5. Save

---

## Step 3: Upload Knowledge Files

Upload these files to **Project Knowledge** (the project's persistent context):

| File | Why it's needed |
|------|----------------|
| `claude-project-setup/url-inventory.md` | So Claude knows every valid URL and never invents paths |
| `claude-project-setup/platform-conventions.md` | Docs platform rules, component names, frontmatter schema |
| `claude-project-setup/feature-glossary.md` | Authoritative product feature names and descriptions |
| `claude-project-setup/existing-seo-audit.md` | Current state — Claude won't redo work or regress |
| `claude-project-setup/style-examples.md` | The target writing style with full examples |

**How to upload:**
1. In the project, click **Add to project knowledge**
2. Upload each `.md` file above
3. Wait for each to finish processing before uploading the next

> Do NOT upload `top-pages-template.md` until you've filled in the traffic data — it's for your reference, not Claude's context.

---

## Step 4: Fill In Traffic Data

Before you start optimizations, get real data:

1. Go to Google Search Console → Performance → Pages
2. Export the top 200 pages by impressions
3. Open `claude-project-setup/top-pages-template.md`
4. Fill in **Monthly Visits** and **Position** for each URL
5. Use this to prioritize: optimize pages with high impressions but poor position (>10) first — that's where the quick wins are

---

## Optimization Workflow (per page)

### One chat per page

Start a **new conversation** inside the Claude Project for each page you're optimizing. Do not use one long conversation for multiple pages — context gets stale.

### What to paste in each conversation

```
I need you to optimize this documentation page for SEO, AEO, and GEO.

URL: /docs/[section]/[page]/
Current page content:

[paste the full MDX file content here, including frontmatter]
```

Claude will return:
1. Optimized frontmatter (title + description)
2. Optimized body with same structure and components intact

### What to do with the output

1. Review the diff — check title, description, and any changed prose
2. Verify no components were removed or rewritten
3. Verify no URLs were invented
4. Verify code blocks are unchanged
5. Copy the optimized content into `src/pages/docs/[path].mdx`
6. Run `pnpm dev` and spot-check the rendered page locally
7. Commit with message: `seo: optimize [page title]`

---

## Prioritization Order

**Batch 1 — Quick wins (high impressions, position 10–30)**
Fill in from your Search Console data, but likely candidates:
- `/docs/quickstart/setup-observability/`
- `/docs/sdk/`
- `/docs/evaluation/`
- `/docs/observe/`
- `/docs/command-center/`
- `/docs/simulation/`

**Batch 2 — Section index pages (all "Overview" pages)**
These have generic titles like `"Overview | Future AGI Docs"` — easy win to differentiate:
- All `/docs/*/` index pages (agent-playground, dataset, optimization, prompt, protect, prototype, etc.)

**Batch 3 — High-value feature pages**
- `/docs/evaluation/features/evaluate/`
- `/docs/evaluation/features/cicd/`
- `/docs/evaluation/features/custom/`
- `/docs/command-center/features/routing/`
- `/docs/command-center/features/guardrails/`
- `/docs/observe/features/alerts/`
- All `/docs/sdk/evals/` pages

**Batch 4 — Built-in eval pages (80 pages)**
These likely have thin content. Optimize in bulk — they follow a consistent pattern so you can batch 3–5 per conversation if they're similar.

**Batch 5 — Integration pages (50+ pages)**
These are mostly install-and-use guides for specific frameworks. Lower priority unless Search Console shows traffic.

**Skip for now:** `/docs/api/*` (177 auto-generated pages) — these serve developers who already know what they're looking for; SEO value is low compared to editorial pages.

---

## QC Checklist (after each batch)

After every 10–20 pages committed, do a quick sanity check:

- [ ] `pnpm build` passes — no MDX syntax errors
- [ ] No `[INVALID]` links (run `pnpm audit-links` or check `scripts/audit-links.mjs`)
- [ ] Page titles are all unique (check for "Overview | Future AGI Docs" duplicates)
- [ ] No description exceeds 160 characters
- [ ] No component was accidentally removed (grep for `<Steps>`, `<CodeGroup>` in changed files)
- [ ] "Future AGI" is spelled correctly everywhere (not FutureAGI or future agi)
- [ ] "Agent Command Center" is used (not Prism)
- [ ] Code blocks are identical to original (git diff the `.mdx` files)

---

## AEO / GEO Specific Notes

### Answer Engine Optimization (AEO)
Claude and Perplexity already have access to your site (see `robots.txt` — ClaudeBot and PerplexityBot are explicitly allowed). For AEO, each page should:
- Answer one specific question directly in the `## About` section
- Use concrete numbers: "76+ metrics", "under 10ms", "45+ frameworks"
- Define terms on first use (AI crawlers surface these as answers)
- The BreadcrumbList JSON-LD is already in place — good

### Generative Engine Optimization (GEO)
The site already has `/llms.txt` and `/llms-full.txt` — these are good. Per-page: use consistent terminology from the feature glossary; avoid synonyms for product names; structured data (TechArticle) is already on every page.

---

## Known Issues to Fix (from SEO Audit)

These are systemic fixes separate from page-by-page optimization:

| Issue | Priority | Fix |
|-------|----------|-----|
| 15+ pages titled "Overview" | High | Batch rename via the project |
| 4+ pages titled "Quickstart" | High | Batch rename via the project |
| `og:type` is "website" not "article" | Medium | Fix in `BaseLayout.astro` line ~54 |
| No `datePublished` in JSON-LD | Low | Add to `BaseLayout.astro` — use file `birthtime` |
| No `FAQPage` schema on `/docs/faq/` | Medium | Add JSON-LD to `faq.mdx` |
| Sitemap has prism URLs not command-center | High | Rebuild after next deploy; verify sitemap output |
| Static OG image for all pages | Low | Out of scope for this project |
| `roles-and-permissions.mdx` missing description | Quick win | Add in 5 minutes |

---

## Tips

- **One page per conversation** — Claude's context is best when focused
- **Always paste the full MDX** — partial content produces incomplete output
- **Trust the components** — never ask Claude to rewrite component usage
- **Verify URLs** — if Claude references a URL not in `url-inventory.md`, flag it
- **Commit often** — small commits are easy to revert if something breaks
- **Use `pnpm build`** before pushing — Astro will catch MDX syntax errors at build time
