# Future AGI Documentation Site

Built with [Astro](https://astro.build), MDX, React islands, and Tailwind CSS v4.

**Live**: https://docs.futureagi.com

---

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server (http://localhost:4321)
npm run dev

# Production build
npm run build

# Preview production build
npm run preview
```

---

## Project Structure

```
product-docs/
├── src/
│   ├── components/docs/     # Reusable MDX components (Card, Tip, Tabs, etc.)
│   ├── layouts/
│   │   ├── BaseLayout.astro # Root HTML layout (fonts, meta, styles)
│   │   └── DocsLayout.astro # Docs page layout (sidebar, TOC, pagination)
│   ├── lib/
│   │   └── navigation.ts   # Sidebar navigation structure
│   ├── pages/docs/          # All documentation pages (MDX)
│   └── styles/
│       └── global.css       # Design tokens & CSS variables
├── public/
│   └── images/docs/         # Documentation images
└── astro.config.mjs
```

---

## Writing Documentation

### Creating a New Page

**1. Create the MDX file** at the appropriate path under `src/pages/docs/`:

```
src/pages/docs/
├── evaluation/
│   ├── index.mdx            → /docs/evaluation
│   ├── overview.mdx          → /docs/evaluation/overview
│   └── builtin/
│       └── audio/
│           ├── index.mdx     → /docs/evaluation/builtin/audio
│           └── audio-quality.mdx → /docs/evaluation/builtin/audio/audio-quality
```

File paths map directly to URLs. `index.mdx` serves at the directory path.

**2. Add frontmatter** at the top of the file:

```mdx
---
layout: ../../layouts/DocsLayout.astro
title: "Your Page Title"
description: "A brief description for search engines and page header"
---
```

The `layout` path must be **relative** to the MDX file. Count directory levels:

| File location | Layout path |
|---|---|
| `src/pages/docs/page.mdx` | `../../layouts/DocsLayout.astro` |
| `src/pages/docs/section/page.mdx` | `../../../layouts/DocsLayout.astro` |
| `src/pages/docs/section/sub/page.mdx` | `../../../../layouts/DocsLayout.astro` |

**3. Import components** you need (after the frontmatter `---`, before content):

```mdx
---
layout: ../../../layouts/DocsLayout.astro
title: "Getting Started"
description: "Set up your first evaluation"
---
import Card from '../../../components/docs/Card.astro'
import CardGroup from '../../../components/docs/CardGroup.astro'
import Note from '../../../components/docs/Note.astro'
import Steps from '../../../components/docs/Steps.astro'
import Step from '../../../components/docs/Step.astro'

Your markdown content starts here...
```

**Important**: There must be a **blank line** between the last `import` statement and the first line of markdown content. Without this, the build will fail with an acorn parse error.

**4. Add the page to navigation** in `src/lib/navigation.ts` (see [Navigation](#navigation) section below).

---

### Markdown Basics

Write standard markdown. The layout handles the `<h1>` from frontmatter `title`, so **start your headings at `##`**:

```mdx
## Section Heading

Regular paragraph text with **bold** and *italic*.

### Subsection

- Bullet list item
- Another item

1. Numbered list
2. Second item

[Link text](/docs/some-page)

![Alt text](/images/docs/section/image.png)
```

---

## Available Components

Import any of these from `src/components/docs/` using relative paths.

### Callouts

```mdx
import Note from '../../../components/docs/Note.astro'
import Tip from '../../../components/docs/Tip.astro'
import Warning from '../../../components/docs/Warning.astro'
import Callout from '../../../components/docs/Callout.astro'
```

```mdx
<Note>
  Informational callout — use for context, prerequisites, or references.
</Note>

<Tip>
  Helpful suggestion — use for best practices or shortcuts.
</Tip>

<Warning>
  Warning — use for common pitfalls or important caveats.
</Warning>

<Callout type="error" title="Breaking Change">
  Error callout — use for breaking changes or critical issues.
</Callout>

<Callout type="success">
  Success callout — use for confirmation messages.
</Callout>
```

**Callout types**: `info` (default), `tip`, `warning`, `error`, `success`

---

### Cards

```mdx
import Card from '../../../components/docs/Card.astro'
import CardGroup from '../../../components/docs/CardGroup.astro'
```

```mdx
<CardGroup cols={3}>
  <Card title="Evaluation" icon="chart-mixed" href="/docs/evaluation">
    Test and measure AI output quality.
  </Card>
  <Card title="Simulation" icon="robot" href="/docs/simulation">
    Simulate conversations at scale.
  </Card>
  <Card title="Dataset" icon="database" href="/docs/dataset">
    Create and manage datasets.
  </Card>
</CardGroup>
```

**Props**:
- `Card`: `title` (required), `href?`, `icon?`
- `CardGroup`: `cols?` — `2`, `3`, or `4` (default: `2`)

---

### Steps

```mdx
import Steps from '../../../components/docs/Steps.astro'
import Step from '../../../components/docs/Step.astro'
```

```mdx
<Steps>
  <Step title="Install the SDK">
    ```bash
    pip install futureagi
    ```
  </Step>
  <Step title="Set your API key">
    ```bash
    export FI_API_KEY="your-key-here"
    ```
  </Step>
  <Step title="Run your first eval">
    ```python
    from fi.evals import Evaluator
    result = Evaluator.run(...)
    ```
  </Step>
</Steps>
```

---

### Tabs

```mdx
import Tabs from '../../../components/docs/Tabs.astro'
import Tab from '../../../components/docs/Tab.astro'
```

**Pattern 1 — With `Tab` children** (recommended):

```mdx
<Tabs>
  <Tab title="Python">
    ```python
    import futureagi
    ```
  </Tab>
  <Tab title="JavaScript">
    ```javascript
    import { FutureAGI } from 'futureagi';
    ```
  </Tab>
</Tabs>
```

**Pattern 2 — With `items` prop and `TabPanel`**:

```mdx
import Tabs from '../../../components/docs/Tabs.astro'
import TabPanel from '../../../components/docs/TabPanel.astro'
```

```mdx
<Tabs items={["Python", "JavaScript"]}>
  <TabPanel index={0}>
    ```python
    import futureagi
    ```
  </TabPanel>
  <TabPanel index={1}>
    ```javascript
    import { FutureAGI } from 'futureagi';
    ```
  </TabPanel>
</Tabs>
```

---

### Accordions

```mdx
import Accordion from '../../../components/docs/Accordion.astro'
import AccordionGroup from '../../../components/docs/AccordionGroup.astro'
```

```mdx
<AccordionGroup>
  <Accordion title="How do I get an API key?">
    Go to **Settings > API Keys** in the Future AGI dashboard.
  </Accordion>
  <Accordion title="What models are supported?">
    We support OpenAI, Anthropic, Google, and more.
  </Accordion>
</AccordionGroup>
```

---

### API Documentation

```mdx
import ParamField from '../../../../components/docs/ParamField.astro'
import ResponseField from '../../../../components/docs/ResponseField.astro'
```

```mdx
## Parameters

<ParamField body="name" type="string" required>
  The name of the evaluation group.
</ParamField>

<ParamField body="description" type="string">
  Optional description for the group.
</ParamField>

<ParamField query="limit" type="integer" default="20">
  Number of results to return.
</ParamField>

## Response

<ResponseField name="id" type="string" required>
  Unique identifier for the created resource.
</ResponseField>
```

**ParamField props**: `body?`, `query?`, `path?`, `header?`, `name?`, `type?`, `required?`, `default?`

---

## Available Icons

Use these with the `icon` prop on `<Card>`:

| Category | Icons |
|---|---|
| **Navigation** | `rocket`, `code`, `book`, `puzzle`, `lightning` |
| **AI** | `robot`, `wand-magic-sparkles`, `brain` |
| **Charts** | `chart-mixed`, `chart-line`, `gauge` |
| **Dev** | `flask`, `play`, `play-circle`, `plug`, `gear` |
| **Monitoring** | `compass`, `eye`, `magnifying-glass`, `search`, `arrows-rotate` |
| **Data** | `database`, `table`, `infinity` |
| **Other** | `shield`, `zap`, `webhook`, `bolt`, `clipboard-list`, `graduation-cap`, `microphone`, `check`, `list-check` |

---

## Navigation

Navigation lives in `src/lib/navigation.ts`. The site uses a **tab-based** structure:

```
Tabs:  [Docs]  [Integrations]  [Cookbooks]  [SDK]  [API]
         |
         └── Groups (sidebar dropdown sections)
              ├── Get Started
              ├── Evaluation
              ├── Observability
              ├── Dataset
              ├── Simulation
              ├── Prompt
              ├── Optimization
              └── ...
```

### Adding a Page to Navigation

Open `src/lib/navigation.ts` and add your page to the appropriate group:

```typescript
// Simple page link
{ title: 'My New Page', href: '/docs/section/my-new-page' },

// Collapsible section with sub-pages
{
  title: 'My Section',
  items: [
    { title: 'Overview', href: '/docs/section/my-section' },
    { title: 'Getting Started', href: '/docs/section/my-section/getting-started' },
    { title: 'Advanced', href: '/docs/section/my-section/advanced' },
  ]
},
```

### Data Structures

```typescript
interface NavItem {
  title: string;      // Display text in sidebar
  href?: string;      // URL path (omit for non-clickable group headers)
  icon?: string;      // Optional icon name
  items?: NavItem[];  // Nested children (creates collapsible section)
}

interface NavGroup {
  group: string;      // Sidebar section heading (shown in dropdown)
  icon?: string;
  items: NavItem[];
}

interface NavTab {
  tab: string;        // Top tab label
  icon: string;
  href: string;       // Base path for the tab
  groups: NavGroup[];
}
```

### Nesting Depth

- **1 level**: Simple page link in sidebar
- **2 levels**: Group header with child pages (collapsible with chevron)
- **3 levels**: Nested collapsible sections (e.g., Built-in Evals > Audio > Audio Quality)

The sidebar auto-expands the section containing the current page.

---

## Images

Place images in `public/images/docs/` organized by section:

```
public/images/docs/
├── tracing/manual/
├── prompt/from-scratch/
├── product-guides/quickstart/
└── n8n/
```

Reference in MDX with absolute paths from `public/`:

```mdx
![Setup screen](/images/docs/tracing/manual/screenshot.png)
```

**Never use relative paths** like `./images/screenshot.png` — they won't resolve in Astro MDX.

---

## Common Pitfalls

### Build fails with "Unexpected character '#'"

Missing blank line between `import` statements and markdown content:

```mdx
---
layout: ../../layouts/DocsLayout.astro
title: "Page"
---
import Note from '../../components/docs/Note.astro'

## Heading starts here
```

The blank line after the import is **required**.

### Build fails with "Unexpected character '<' or '='"

Raw `<` and `<=` in prose get parsed as JSX. Wrap in backticks:

```mdx
<!-- Bad -->
The value must be <= 100.

<!-- Good -->
The value must be `<= 100`.
```

### Layout path is wrong

Count the directory depth from your MDX file to `src/layouts/`:

```
src/pages/docs/page.mdx                    → ../../layouts/DocsLayout.astro
src/pages/docs/section/page.mdx            → ../../../layouts/DocsLayout.astro
src/pages/docs/section/sub/page.mdx        → ../../../../layouts/DocsLayout.astro
```

### Page exists but doesn't appear in sidebar

Add it to `src/lib/navigation.ts`. Pages not in navigation still render at their URL but won't show in the sidebar or pagination.

### Stray `---` in content

A `---` on its own line after frontmatter gets parsed as a second frontmatter delimiter. Use `***` or `<hr />` for horizontal rules instead.

---

## Auto-Generated Features

The `DocsLayout` automatically handles these — you don't need to add them:

- **Page title** (`<h1>`) from frontmatter `title`
- **Table of Contents** extracted from `##` and `###` headings
- **Previous / Next pagination** based on navigation order
- **Page feedback widget** (thumbs up/down)
- **Search** via Pagefind (indexed at build time)
- **Syntax highlighting** via Shiki (`github-dark-default` theme)

---

## Full Page Example

A complete, well-structured doc page:

```mdx
---
layout: ../../../layouts/DocsLayout.astro
title: "Create a Dataset"
description: "Learn how to create and populate datasets for evaluation"
---
import Card from '../../../components/docs/Card.astro'
import CardGroup from '../../../components/docs/CardGroup.astro'
import Note from '../../../components/docs/Note.astro'
import Tip from '../../../components/docs/Tip.astro'
import Steps from '../../../components/docs/Steps.astro'
import Step from '../../../components/docs/Step.astro'
import Tabs from '../../../components/docs/Tabs.astro'
import Tab from '../../../components/docs/Tab.astro'

Datasets are structured collections of inputs and expected outputs used
to evaluate your AI application.

<Note>
  You need an API key before creating datasets.
  See [Installation](/docs/installation).
</Note>

## Prerequisites

- Future AGI account with API access
- Python 3.8+ installed

## Create Your First Dataset

<Steps>
  <Step title="Install the SDK">
    ```bash
    pip install futureagi
    ```
  </Step>
  <Step title="Create the dataset">
    <Tabs>
      <Tab title="Python">
        ```python
        from fi.datasets import Dataset

        ds = Dataset.create(
            name="my-dataset",
            columns=["input", "expected_output"]
        )
        ```
      </Tab>
      <Tab title="Platform UI">
        Navigate to **Datasets > Create New** in your dashboard.
      </Tab>
    </Tabs>
  </Step>
</Steps>

<Tip>
  Start with a small dataset (10-20 rows) to validate your eval setup
  before scaling.
</Tip>

## Next Steps

<CardGroup cols={2}>
  <Card title="Add Rows" icon="table" href="/docs/dataset/add-rows">
    Populate your dataset with test cases.
  </Card>
  <Card title="Run Evaluations" icon="chart-mixed" href="/docs/dataset/evaluate-dataset">
    Evaluate your AI outputs against the dataset.
  </Card>
</CardGroup>
```

---

## Development Workflow

1. **Create/edit** MDX file in `src/pages/docs/`
2. **Add to navigation** in `src/lib/navigation.ts`
3. **Add images** to `public/images/docs/` if needed
4. **Run `npm run dev`** and verify in browser
5. **Run `npm run build`** to check for errors before pushing

---

## Commands Reference

| Command | Action |
|---|---|
| `npm install` | Install dependencies |
| `npm run dev` | Start dev server at `localhost:4321` |
| `npm run build` | Production build to `./dist/` (includes Pagefind indexing) |
| `npm run preview` | Preview production build locally |
