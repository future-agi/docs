# Writing Documentation — Internal Guide

This guide covers everything you need to create and maintain pages on [docs.futureagi.com](https://docs.futureagi.com). Read this before writing your first page.

---

## Quick Start (30 seconds)

```bash
# 1. Create a new page (auto-adds to navigation)
pnpm new-doc docs/section/page-name "Page Title"

# 2. Write content in the created .mdx file (no imports needed)

# 3. Preview
pnpm dev

# 4. Check for broken links before pushing
pnpm audit-links
```

That's it. No layout paths. No import statements. Just frontmatter + content.

---

## How It Works

Every `.mdx` file in `src/pages/docs/` becomes a page. A Vite plugin automatically handles:

- **Layout injection** — correct `DocsLayout.astro` path calculated from file depth
- **Component imports** — scans your content for `<ComponentName` and adds imports
- **29 components** available with zero setup

**You write:**

```mdx
---
title: "My Page"
description: "What this page covers in 120-160 characters."
---

Some intro text.

<Note>
  This just works. No imports needed.
</Note>
```

**The build system adds:**

```mdx
---
layout: ../../../layouts/DocsLayout.astro   ← auto-injected
title: "My Page"
description: "What this page covers in 120-160 characters."
---
import Note from '../../../components/docs/Note.astro'   ← auto-injected

Some intro text.

<Note>
  This just works. No imports needed.
</Note>
```

---

## Page Structure

### Frontmatter (Required)

Every page needs `title` and `description` in the frontmatter block:

```mdx
---
title: "Create a Dataset"
description: "Learn how to create and populate datasets for evaluation in Future AGI."
---
```

| Field | Required | Notes |
|-------|----------|-------|
| `title` | Yes | Rendered as the `<h1>`, used in sidebar, browser tab, OG tags |
| `description` | Yes | Used in meta tags, search results, page header. Keep to 120-160 chars |

> **SEO**: Every page MUST have a description. Pages without descriptions hurt search rankings.

### Content Rules

- **Start at `##`** — the `<h1>` comes from the `title` field. Never use `# Heading` in content.
- **Blank line required** between frontmatter `---` and first content line
- **No `---`** horizontal rules in content (gets parsed as frontmatter). Use `***` or `<hr />` instead.
- **Escape `<` and `<=`** in prose — wrap in backticks: `` `<= 100` `` not `<= 100`

---

## File & URL Mapping

```
src/pages/docs/
├── index.mdx                    → /docs
├── installation.mdx             → /docs/installation
├── evaluation/
│   ├── index.mdx                → /docs/evaluation
│   └── builtin/
│       ├── index.mdx            → /docs/evaluation/builtin
│       └── audio/
│           └── audio-quality.mdx → /docs/evaluation/builtin/audio/audio-quality
```

- `index.mdx` serves at the directory URL
- File path = URL path (no config needed)
- Use lowercase, hyphenated names: `my-cool-page.mdx` not `MyCoolPage.mdx`

---

## Navigation

Navigation is defined in `src/lib/navigation.ts`. The site uses **tabs → groups → items**:

```
[Docs]  [Integrations]  [Cookbooks]  [SDK]  [API]   ← Tabs
  │
  ├── Get Started          ← Group (sidebar section heading)
  │   ├── Introduction     ← Item (page link)
  │   └── Quickstart       ← Item (collapsible with children)
  │       ├── Setup Observability
  │       └── Run Evals
  │
  ├── Evaluation           ← Group
  │   ├── Overview
  │   └── Features         ← Nested collapsible
  │       ├── Built-in Evals
  │       └── Custom Evals
```

### Adding a Page to Navigation

The `pnpm new-doc` command does this automatically. To do it manually:

```typescript
// Simple page link
{ title: 'My New Page', href: '/docs/section/my-page' },

// Collapsible section with children
{
  title: 'My Section',
  items: [
    { title: 'Overview', href: '/docs/section/my-section' },
    { title: 'Getting Started', href: '/docs/section/my-section/getting-started' },
  ]
},
```

### Data Types

```typescript
interface NavItem {
  title: string;       // Display text in sidebar
  href?: string;       // URL (omit for non-clickable group headers)
  icon?: string;       // Optional icon name
  items?: NavItem[];   // Children (creates collapsible section)
}

interface NavGroup {
  group: string;       // Section heading in sidebar
  icon?: string;
  items: NavItem[];
}

interface NavTab {
  tab: string;         // Top tab label (Docs, Integrations, etc.)
  icon: string;
  href: string;        // Base path
  groups: NavGroup[];
}
```

### Nesting Depth

- **1 level**: Page link in sidebar
- **2 levels**: Collapsible group with children (chevron icon)
- **3 levels**: Nested collapsible (e.g., Built-in Evals → Audio → Audio Quality)

---

## Components Reference

All components are auto-imported. Just write `<ComponentName>` in your MDX.

### Callouts

Use for important information, tips, or warnings.

```mdx
<Note>
  Informational — context, prerequisites, references.
</Note>

<Tip>
  Best practices, shortcuts, helpful suggestions.
</Tip>

<Warning>
  Common pitfalls, important caveats, deprecation notices.
</Warning>

<Callout type="error" title="Breaking Change">
  Critical issues, breaking changes.
</Callout>

<Callout type="success">
  Confirmation, success states.
</Callout>
```

**Types**: `info` (default), `tip`, `warning`, `error`, `success`

### Cards

Link cards for navigation and feature showcases.

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

| Prop | Type | Default | Notes |
|------|------|---------|-------|
| `Card.title` | string | required | Card heading |
| `Card.href` | string | — | Makes card clickable |
| `Card.icon` | string | — | Icon name (see Icons section) |
| `CardGroup.cols` | 2 \| 3 \| 4 | 2 | Grid columns |

> `CardGrid` is an alias for `CardGroup` — they work identically.

### Steps

Numbered step-by-step instructions.

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

Steps auto-number and render with a connecting vertical line.

### Tabs

Switch between content variants (languages, platforms, etc.).

**Pattern 1 — Tab children (recommended):**

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

**Pattern 2 — Items prop with TabPanel:**

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

### Accordions

Collapsible content sections.

```mdx
<AccordionGroup>
  <Accordion title="How do I get an API key?">
    Go to **Settings > API Keys** in the dashboard.
  </Accordion>
  <Accordion title="What models are supported?">
    We support OpenAI, Anthropic, Google, and more.
  </Accordion>
</AccordionGroup>
```

Set `defaultOpen` to expand by default:

```mdx
<Accordion title="Always visible" defaultOpen>
  This section starts expanded.
</Accordion>
```

### API Documentation

Document API parameters and response fields.

```mdx
## Parameters

<ParamField body="name" type="string" required>
  The name of the evaluation group.
</ParamField>

<ParamField query="limit" type="integer" default="20">
  Number of results to return.
</ParamField>

<ParamField header="Authorization" type="string" required>
  Bearer token for authentication.
</ParamField>

## Response

<ResponseField name="id" type="string" required>
  Unique identifier for the created resource.
</ResponseField>

<ResponseField name="status" type="string">
  Current status of the resource.
</ResponseField>
```

**ParamField location props** (use one): `body`, `query`, `path`, `header`

### API Endpoint Badge

```mdx
<ApiEndpoint method="POST" path="/api/v1/evaluate" />
```

Renders a colored badge: `POST /api/v1/evaluate`

### Code Blocks

Standard markdown code blocks work with syntax highlighting (Shiki, `github-dark-default` theme):

````mdx
```python
from fi.evals import Evaluator
result = Evaluator.run(input="Hello", output="Hi there")
```
````

For code with a title bar:

```mdx
<CodeBlock title="example.py">
  ```python
  from fi.evals import Evaluator
  ```
</CodeBlock>
```

For tabbed code blocks:

```mdx
<CodeGroup>
  ```python title="Python"
  from fi.evals import Evaluator
  ```
  ```javascript title="JavaScript"
  import { Evaluator } from 'futureagi';
  ```
</CodeGroup>
```

### Other Components

| Component | Usage | What it does |
|-----------|-------|-------------|
| `<TLDR>` | `<TLDR>Key points here</TLDR>` | Summary box with accent border |
| `<Check>` | `<Check>Feature available</Check>` | Green checkmark callout |
| `<Prerequisites>` | `<Prerequisites>- Node 16+\n- API key</Prerequisites>` | Checklist-style prerequisites box |
| `<Expandable>` | `<Expandable title="Details">...</Expandable>` | Collapsible section (like Accordion but simpler) |
| `<Tooltip>` | `<Tooltip tip="explanation">term</Tooltip>` | Hover tooltip on underlined text |
| `<Update label="v2.0">` | Wrap changelog content | Changelog entry with version badge |
| `<Icon icon="check">` | Inline icon | Renders SVG icon inline |

---

## Available Icons

Use with `icon` prop on `<Card>`:

| Category | Icons |
|----------|-------|
| **Navigation** | `rocket`, `code`, `book`, `puzzle`, `lightning` |
| **AI** | `robot`, `wand-magic-sparkles`, `brain` |
| **Charts** | `chart-mixed`, `chart-line`, `gauge` |
| **Dev** | `flask`, `play`, `play-circle`, `plug`, `gear` |
| **Monitoring** | `compass`, `eye`, `magnifying-glass`, `search`, `arrows-rotate` |
| **Data** | `database`, `table`, `infinity` |
| **Other** | `shield`, `zap`, `webhook`, `bolt`, `clipboard-list`, `graduation-cap`, `microphone`, `check`, `list-check`, `github`, `google`, `wrench`, `comments` |

---

## Images

Place images in `public/images/docs/` organized by section:

```
public/images/docs/
├── tracing/manual/screenshot.png
├── prompt/from-scratch/step1.png
└── evaluation/custom-eval.png
```

Reference with absolute paths from `public/`:

```mdx
![Descriptive alt text](/images/docs/tracing/manual/screenshot.png)
```

> **Never** use relative paths like `./images/foo.png` — they don't resolve in Astro MDX.
>
> **Always** use descriptive alt text for SEO. Don't use filenames like `image.png`.

---

## Auto-Generated Features

The layout automatically provides — you don't need to add these:

- **Page title** (`<h1>`) from frontmatter `title`
- **Breadcrumb navigation** (visible + JSON-LD schema)
- **Table of Contents** from `##` and `###` headings (sticky right sidebar)
- **Previous / Next pagination** based on navigation order
- **Page feedback widget** (thumbs up/down)
- **Copy page dropdown** (copy as markdown/link)
- **Canonical URL** and **Open Graph** meta tags
- **Structured data** (TechArticle JSON-LD)
- **Search indexing** via Pagefind

---

## Full Page Example

```mdx
---
title: "Create a Dataset"
description: "Learn how to create and populate datasets for evaluation in Future AGI."
---

Datasets are structured collections of inputs and expected outputs used
to evaluate your AI application.

<Note>
  You need an API key before creating datasets.
  See [Installation](/docs/installation).
</Note>

## Prerequisites

- Future AGI account with API access
- Python 3.8+

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

## Workflow

1. **Create page**: `pnpm new-doc docs/section/page "Title"`
2. **Write content** — use components directly, no imports
3. **Add images** to `public/images/docs/` if needed
4. **Preview**: `pnpm dev`
5. **Audit links**: `pnpm audit-links` (catches broken links before deploy)
6. **Build check**: `pnpm build` (catches syntax errors)
7. **Push** to trigger deploy

---

## Commands

| Command | What it does |
|---------|-------------|
| `pnpm dev` | Start dev server at `localhost:4321` |
| `pnpm build` | Production build to `./dist/` |
| `pnpm preview` | Preview production build locally |
| `pnpm new-doc <path> [title]` | Create a new doc page + add to navigation |
| `pnpm audit-links` | Find broken links and orphan pages |
| `pnpm audit-links --verbose` | Also list orphan pages |

---

## Common Pitfalls

### Build fails with "Unexpected character '#'"

Missing blank line between frontmatter and content:

```mdx
---
title: "Page"
---
                    ← this blank line is REQUIRED
## Heading here
```

### Build fails with "Unexpected character '<'"

Raw `<` or `<=` in prose gets parsed as JSX. Wrap in backticks:

```mdx
<!-- Bad -->
The value must be <= 100.

<!-- Good -->
The value must be `<= 100`.
```

### Page exists but not in sidebar

Add it to `src/lib/navigation.ts`. Pages not in navigation still render at their URL but won't show in sidebar or pagination.

### Stray `---` in content

A `---` on its own line gets parsed as a frontmatter delimiter. Use `***` or `<hr />` for horizontal rules.

### Link goes to 404

Run `pnpm audit-links` to find broken links. Common causes:
- Old path from Mintlify migration
- Missing leading `/` in href
- Page was moved/renamed but links weren't updated

---

## API Reference Pages

API endpoint pages use a special two-column layout with interactive code panels. This section covers everything you need to write a new API page.

### How the Layout Works

API pages render in a **two-column layout**:

- **Left column** -- Your documentation content: authentication, parameters, request body, response fields, errors
- **Right column** -- Auto-generated code snippets (cURL, Python, JavaScript, Go) and a response preview, built from your `<ApiPlayground>` props

The right column is generated automatically from the `<ApiPlayground>` component. You never write code examples manually.

A **"Try it"** button opens a modal where users can fill in parameter values and execute real API calls against the endpoint.

### Page Structure

Every API page follows this order:

```
1. Frontmatter (title, description)
2. <ApiPlayground> (endpoint badge + right panel data)
3. <ApiSection title="Authentication"> with <ParamField>
4. <ApiSection title="Path parameters"> (if any) with <ParamField>
5. <ApiSection title="Query parameters"> (if any) with <ParamField>
6. <ApiSection title="Request body"> (if POST/PUT/PATCH) with <ParamField>
7. <ApiSection title="Response"> with <ResponseField>
8. <ApiSection title="Errors"> with <ParamField>
```

No imports needed -- all components are auto-injected.

### Component Reference

#### `<ApiPlayground>`

Renders the endpoint badge in the left column and drives the entire right column (code snippets, response preview, Try It modal).

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `method` | `"GET" \| "POST" \| "PUT" \| "DELETE" \| "PATCH"` | Yes | HTTP method |
| `endpoint` | `string` | Yes | API path, e.g. `/model-hub/eval-groups/` |
| `baseUrl` | `string` | No | Defaults to `https://api.futureagi.com` |
| `parameters` | `array` | No | Query/path parameters array (for Try It form) |
| `requestBody` | `object` | No | Example request body JSON (for code snippets + Try It) |
| `responseExample` | `object` | No | Example response JSON (displayed in right column) |
| `responseStatus` | `number` | No | Response status code. Defaults to `200` |
| `responseStatusText` | `string` | No | Response status text (e.g. `"Created"`). Auto-derived if omitted |

#### `<ApiSection>`

Section divider with title and optional status badge. Wraps `<ParamField>` or `<ResponseField>` children.

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `title` | `string` | Yes | Section heading. Common values: `"Authentication"`, `"Request body"`, `"Path parameters"`, `"Query parameters"`, `"Response"`, `"Errors"` |
| `status` | `number` | No | HTTP status code badge (e.g. `200`, `201`) |
| `statusText` | `string` | No | Status text next to the code (e.g. `"OK"`, `"Created"`) |

#### `<ParamField>`

Displays a single parameter with name, type, required/optional badge, and description.

**Location props** (use exactly one to specify where the param lives):

| Prop | Description |
|------|-------------|
| `body="name"` | Request body field |
| `query="name"` | URL query parameter |
| `path="name"` | URL path parameter (e.g. `{id}`) |
| `header="name"` | HTTP header |
| `name="name"` | Generic (use for auth headers or error codes) |

**Other props:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `type` | `string` | -- | Data type display (e.g. `"string"`, `"integer"`, `"array of string"`) |
| `required` | `boolean` | `false` | Shows "Required" badge |
| `optional` | `boolean` | -- | Shows "Optional" badge (default when `required` is not set) |
| `default` | `string` | -- | Shows "Defaults to X" |
| `constraint` | `string` | -- | Shows constraint code (e.g. `"0-1000"`) |
| `enum` | `string[]` | -- | Shows "Allowed values" list. Must be a JSX array: `enum={["a", "b"]}` |

#### `<ResponseField>`

Displays a single response field. Same visual style as `<ParamField>`.

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `name` | `string` | Yes | Field name |
| `type` | `string` | No | Data type |
| `required` | `boolean` | No | Shows "Required" badge |

#### `<ApiCollapsible>`

Hides nested properties behind a toggle button. Use inside `<ApiSection>` to collapse optional sub-fields.

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `title` | `string` | `"Show properties"` | Toggle button label, e.g. `"Show 3 properties"` |

### Full Example: POST Endpoint

```mdx
---
title: "Create Evaluation Group"
description: "Creates a new evaluation group within the user's workspace."
---

<ApiPlayground
  method="POST"
  endpoint="/model-hub/eval-groups/"
  baseUrl="https://api.futureagi.com"
  requestBody={{
    "name": "my-eval-group",
    "description": "Quality checks for chatbot",
    "eval_template_ids": ["uuid-1", "uuid-2"]
  }}
  responseExample={{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "my-eval-group",
    "description": "Quality checks for chatbot",
    "eval_template_ids": ["uuid-1", "uuid-2"],
    "workspace_id": "ws-123",
    "created_at": "2026-03-15T10:30:00Z"
  }}
  responseStatus={201}
  responseStatusText="Created"
/>

<ApiSection title="Authentication">
  <ParamField name="Authorization" type="Bearer" required>
    Include your API key in the `Authorization` header as `Bearer <token>`. Retrieve your API Key from the [Dashboard](https://app.futureagi.com).
  </ParamField>
</ApiSection>

<ApiSection title="Request body">
  <ParamField body="name" type="string" required>
    The name of the evaluation group. Must be unique within the workspace.
  </ParamField>

  <ParamField body="description" type="string" optional>
    An optional description for the evaluation group.
  </ParamField>

  <ParamField body="eval_template_ids" type="array of string" required>
    A list of evaluation template UUIDs to include in this group.
  </ParamField>

  <ParamField body="config" type="object" optional>
    Optional configuration for the evaluation group.
  </ParamField>
  <ApiCollapsible title="Show 3 properties">
    <ParamField body="config.threshold" type="number" optional>
      The minimum score threshold (0.0 to 1.0).
    </ParamField>
    <ParamField body="config.retry_count" type="integer" optional>
      Number of retry attempts. Default: 0.
    </ParamField>
    <ParamField body="config.timeout_seconds" type="integer" optional>
      Timeout in seconds. Default: 300.
    </ParamField>
  </ApiCollapsible>
</ApiSection>

<ApiSection title="Response" status={201} statusText="Created">
  <ResponseField name="id" type="string" required>
    Unique identifier (UUID) for the created evaluation group.
  </ResponseField>
  <ResponseField name="name" type="string" required>
    The name of the evaluation group.
  </ResponseField>
  <ResponseField name="workspace_id" type="string" required>
    The workspace this group belongs to.
  </ResponseField>
  <ResponseField name="created_at" type="datetime" required>
    ISO 8601 timestamp of when the group was created.
  </ResponseField>
</ApiSection>

<ApiSection title="Errors">
  <ParamField name="400" type="Bad Request">
    The request data is invalid or an evaluation group with the same name already exists.
  </ParamField>
  <ParamField name="401" type="Unauthorized">
    Authentication credentials were not provided or are invalid.
  </ParamField>
  <ParamField name="403" type="Forbidden">
    You do not have permission to create evaluation groups in this workspace.
  </ParamField>
</ApiSection>
```

### Full Example: GET Endpoint with Query Parameters

```mdx
---
title: "List Evaluation Groups"
description: "Retrieves a paginated list of evaluation groups for the user's workspace."
---

<ApiPlayground
  method="GET"
  endpoint="/model-hub/eval-groups/"
  baseUrl="https://api.futureagi.com"
  parameters={[
    {"name": "name", "in": "query", "required": false, "description": "Filter by name.", "type": "string"},
    {"name": "page_size", "in": "query", "required": false, "description": "Results per page.", "type": "integer"},
    {"name": "page_number", "in": "query", "required": false, "description": "Page number.", "type": "integer"}
  ]}
  responseExample={{
    "data": [],
    "total_count": 42,
    "total_pages": 5
  }}
  responseStatus={200}
  responseStatusText="OK"
/>

<ApiSection title="Authentication">
  <ParamField name="Authorization" type="Bearer" required>
    Include your API key in the `Authorization` header as `Bearer <token>`. Retrieve your API Key from the [Dashboard](https://app.futureagi.com).
  </ParamField>
</ApiSection>

<ApiSection title="Query parameters">
  <ParamField query="name" type="string" optional>
    Filter evaluation groups by name (case-insensitive search).
  </ParamField>
  <ParamField query="page_size" type="integer" optional default="20">
    The number of results to return per page.
  </ParamField>
  <ParamField query="page_number" type="integer" optional default="1">
    The page number to retrieve.
  </ParamField>
</ApiSection>

<ApiSection title="Response" status={200} statusText="OK">
  <ResponseField name="data" type="array of object" required>
    The list of evaluation groups.
  </ResponseField>
  <ResponseField name="total_count" type="integer" required>
    Total number of evaluation groups matching the criteria.
  </ResponseField>
  <ResponseField name="total_pages" type="integer" required>
    Total number of pages.
  </ResponseField>
</ApiSection>

<ApiSection title="Errors">
  <ParamField name="401" type="Unauthorized">
    Authentication credentials were not provided or are invalid.
  </ParamField>
  <ParamField name="500" type="Internal Server Error">
    An unexpected error occurred.
  </ParamField>
</ApiSection>
```

### How to Add Response Examples

The `responseExample` prop on `<ApiPlayground>` drives the response preview panel in the right column. It should be a representative JSON response:

```mdx
<ApiPlayground
  method="GET"
  endpoint="/model-hub/scores/"
  responseExample={{
    "id": "abc-123",
    "source_type": "trace",
    "value": { "rating": 5 },
    "created_at": "2026-03-15T10:30:00Z"
  }}
  responseStatus={200}
  responseStatusText="OK"
/>
```

Key rules:
- Use **double braces** `{{ }}` around the JSON (outer braces = JSX expression, inner braces = object literal)
- Include realistic placeholder values, not `"string"` or `"your-value"`
- Match the `responseStatus` to the success status code documented in the Response section
- If the endpoint returns no body (e.g. `204 No Content`), omit `responseExample`

### How the "Try It" Modal Works

The `parameters` prop on `<ApiPlayground>` defines what form fields appear in the Try It modal. Users can fill in values and execute the request directly.

```mdx
<ApiPlayground
  method="GET"
  endpoint="/model-hub/annotation-queues/{queue_id}/items/"
  parameters={[
    { name: "queue_id", type: "string", description: "Queue UUID", required: true },
    { name: "status", type: "string", description: "Filter by status" },
    { name: "page_size", type: "integer", description: "Results per page" }
  ]}
/>
```

For POST/PUT endpoints, the `requestBody` prop pre-fills the request body editor in the modal.

### Checklist for New API Pages

1. Add frontmatter with `title` and `description`
2. Add `<ApiPlayground>` with correct `method`, `endpoint`, and example data
3. Add Authentication section (Bearer or API Key)
4. Add parameter sections (path, query) if the endpoint has URL params
5. Add Request body section if POST/PUT/PATCH
6. Add Response section with `<ResponseField>` entries for each field
7. Add Errors section with common error codes (400, 401, 403, 404, 500)
8. Add the page to `src/lib/navigation.ts` under the API tab
9. Run `pnpm build` to verify the page renders correctly
10. Never write code example sections -- they are auto-generated
