# Documentation Style Guide

This guide defines how to write documentation for Future AGI. Every page should be useful to three audiences: a developer who wants technical depth, a non-technical reader who needs to follow along, and an AI agent that needs to parse instructions and take action.

---

## Page Types

Every product section follows this structure in the sidebar:

```
Product Name
├── Overview
├── Concepts (one or more)
└── Features (one or more)
```

Each page type has a different job. Do not mix them.

### Overview

**Job**: Tell the reader what this product does, why they'd use it, and where to go next.

**Structure**:

```
## About
One paragraph explaining what the product does. No jargon. A non-technical person
should understand this paragraph.

If a video exists, embed it here with a descriptive title attribute.

## [Optional: Key concept or distinction]
If there's one core idea the reader needs before going further, explain it here.
For example, Dataset has "Column Types" (static vs dynamic). Keep it short.

## How [Product] Connects to Other Features
Bullet list showing how this product relates to evaluation, observability,
optimization, etc. Each bullet links to the relevant product page.

## Getting Started
CardGroup linking to the main feature pages.

## Next Steps
Bullet list linking to concept pages, quickstarts, or cookbooks.
```

**What belongs here**: High-level explanation, cross-links, navigation cards.

**What does NOT belong here**: Step-by-step instructions, code examples, screenshots of UI flows, configuration details.

**Video**: Yes, if one exists. Embed at the top of the page right after the About paragraph. Always set a descriptive `title` attribute (not "YouTube video player").

**Screenshots**: No. Overview pages are text and cards.

**Code examples**: No. Link to the quickstart or feature pages instead.

---

### Concept Pages

**Job**: Explain a single idea so the reader understands *what* it is and *why* it matters. Concept pages teach. They do not show how to do things step by step.

**Structure**:

```
## About
What this concept is. Use plain language first, then add the technical detail.
Start with a concrete example (table, diagram, or short illustration) so the
reader sees the concept before reading the explanation.

## When to use
Bullet list of practical scenarios. Each bullet should describe a real situation,
not a generic benefit.

Bad:  "Efficiency: Reduces manual data entry"
Good: "You need model outputs for 10,000 rows and can't run them one by one"

## [Concept-specific sections]
Details about the concept. Use tables for structured information (types, modes,
parameters). Use prose for explanations of how things work.

## Next Steps
Links to sibling concept pages and related feature pages.
```

**What belongs here**: Explanations, tables showing types/modes/options, concrete examples illustrating the concept.

**What does NOT belong here**: Step-by-step instructions, SDK code for performing actions, screenshots of UI workflows.

**Video**: No. Concept pages are text.

**Screenshots**: Only if showing a visual concept (e.g. a pipeline diagram, an architecture overview). Not for UI walkthroughs.

**Code examples**: Only if the code IS the concept (e.g. showing what a JSON config looks like, or what a dataset table contains). Not for "here's how to create one."

---

### Feature Pages

**Job**: Show the reader how to do something specific. Feature pages are step-by-step instructions. A reader should be able to follow the page and complete the task.

**Structure**:

```
## About
One or two sentences explaining what this feature does. Link to the concept
page if the reader needs background.

## [Steps or Configuration]
The actual instructions. Use one of these formats:

- Steps component for sequential tasks (set up, configure, run)
- Tabs component for showing Dashboard vs SDK vs cURL approaches
- Tables for configuration parameters

## [Examples or specific sub-features]
Show concrete examples. Every code block should be copy-pasteable and runnable.

## Next Steps
Links to related features, concept pages, or cookbooks.
```

**What belongs here**: Step-by-step instructions, code examples, screenshots of the UI, configuration parameters, expected outputs.

**What does NOT belong here**: Long explanations of why this feature exists (that's the concept page), marketing language, comparisons to competitors.

**Video**: Only if the feature has a complex UI flow that's hard to convey with screenshots. Prefer screenshots for simple flows.

**Screenshots**: Yes. Add a screenshot after each major step in a UI workflow. Every screenshot should have alt text describing what it shows.

**Code examples**: Yes. Every feature page should show how to do the task via code. Use tabbed CodeGroup for Python/TypeScript/cURL where applicable. Every code block must be:
- Complete (can be copied and run as-is)
- Consistent (use the same variable names, API keys, and patterns across all pages)
- Commented only where the logic isn't obvious

---

## Writing Rules

### Headings

- First heading on every page is `## About`
- Use `##` for top-level sections, `###` for subsections
- Do not bold headings (`## **Bad**` vs `## Good`)
- Do not use "What is it?", "What it is", or "Purpose" as headings

### Formatting

- No em-dashes. Use colons, periods, or commas instead.
  - Bad: `**PII Detection** — Detects emails and SSNs`
  - Good: `**PII Detection**: Detects emails and SSNs`

- No excessive bold. Bold the term being defined, not the explanation.
  - Bad: `**Immutable:** Values do not change unless **updated manually**.`
  - Good: `**Immutable**: Values do not change unless updated manually.`

- Use tables for structured data (parameters, types, modes). Use bullets for lists of items. Do not use bullets when a table would be clearer.

- Use `<Note>` for important caveats. Use `<Tip>` for optional helpful advice. Use `<Warning>` for things that can break or cost money. Do not overuse them.

### Tone

- Write like you're explaining to a colleague, not selling to a customer.
- No marketing language: "powerful", "seamless", "cutting-edge", "game-changer", "empowers you to", "ensuring flexibility, scalability, and usability".
- No filler sentences: "This section will walk you through the process of..." Just start the process.
- No trailing summaries: "In this guide, we covered X, Y, and Z." The reader just read it.
- Say "you" not "users" or "the user".
- Use active voice: "Run the evaluation" not "The evaluation can be run".

### Content Quality

- Every claim should be specific. Replace vague statements with concrete ones.
  - Bad: "Prism adds minimal latency"
  - Good: "Prism adds ~11 microseconds of overhead per request"

- Do not fabricate technical details. If you don't have confirmed specs for an SDK method, API endpoint, or configuration option, do not write it. Flag it as needing input from the developer instead.

- Do not repeat content across pages. If a concept is explained on the concept page, link to it from the feature page. Don't re-explain it.

- Every internal link must resolve to an existing page. Run `node scripts/audit-links.mjs` to check.

### Examples

Every example should be concrete and realistic. Avoid placeholder content that doesn't teach anything.

- Bad: `"Hello, how are you?"` as a prompt example (too generic)
- Good: `"What is the capital of France?"` (simple but demonstrates the input/output pattern)

- Bad: `project_name="FUTURE_AGI"` (not a real project name)
- Good: `project_name="my-chatbot"` (realistic)

For dataset examples, use tables that show actual data, not descriptions of data.

### Code Examples

- Always use `<CodeGroup>` with `titles={["Python", "TypeScript", "cURL"]}` when showing SDK usage
- Python and TypeScript are required. cURL is required for API/gateway pages. cURL is optional for platform UI pages.
- Every code block should include the import/setup lines. Don't assume the reader has seen a previous page.
- Use consistent placeholder values:
  - API keys: `"YOUR_API_KEY"`, `"sk-prism-your-api-key-here"`
  - Project names: `"my-chatbot"`, `"my-project"`
  - Base URLs: Use the actual production URL, not localhost

### Page Flow

Pages should flow from simple to advanced:

1. Start with what this is (About)
2. Show the simplest way to use it (basic example or first step)
3. Add configuration options and parameters
4. Show advanced usage or edge cases
5. Link to what to do next (Next Steps)

A reader who only reads the first two sections should still get value. A reader who reads the whole page should have complete knowledge.

---

## Checklist

Before publishing any page, verify:

- [ ] Page starts with `## About`
- [ ] No em-dashes anywhere
- [ ] No excessive bold
- [ ] No marketing language or filler sentences
- [ ] All internal links resolve (run audit-links)
- [ ] Code examples are complete and copy-pasteable
- [ ] Tables used for structured data instead of long bullet lists
- [ ] Next Steps section at the bottom
- [ ] Page follows the right type (overview / concept / feature)
- [ ] A non-technical reader can understand the About section
- [ ] A developer can find the code example they need
- [ ] An AI agent can parse the steps and take action
