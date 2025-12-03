# Documentation Contributor Guide

This guide explains how to add and edit documentation for the Future AGI docs site. No prior web development experience is required.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Project Structure](#project-structure)
3. [Writing Documentation Pages](#writing-documentation-pages)
4. [Adding Pages to Navigation](#adding-pages-to-navigation)
5. [Using Components](#using-components)
6. [Formatting & Markdown](#formatting--markdown)
7. [Images & Assets](#images--assets)
8. [Running Locally](#running-locally)
9. [Common Tasks](#common-tasks)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

- [Node.js](https://nodejs.org/) version 18 or higher
- A code editor (we recommend [VS Code](https://code.visualstudio.com/))
- Basic familiarity with Markdown

### First-Time Setup

```bash
# Clone the repository
git clone <repository-url>
cd landing-page

# Install dependencies
npm install

# Start the development server
npm run dev
```

Open http://localhost:4321 in your browser to see the site.

---

## Project Structure

```
landing-page/
├── src/
│   ├── pages/              # All documentation pages go here
│   │   ├── index.astro     # Homepage (/)
│   │   ├── changelog.astro # Changelog page
│   │   └── docs/           # Documentation pages
│   │       ├── quickstart.mdx
│   │       ├── installation.mdx
│   │       ├── api.mdx
│   │       └── evaluate/   # Nested section
│   │           ├── index.mdx    # Section overview
│   │           └── metrics.mdx  # Sub-page
│   │
│   ├── components/         # Reusable UI components
│   │   └── docs/           # Documentation-specific components
│   │       ├── Callout.astro
│   │       ├── Card.astro
│   │       └── CodeGroup.astro
│   │
│   ├── layouts/            # Page layouts
│   │   ├── BaseLayout.astro
│   │   └── DocsLayout.astro
│   │
│   ├── lib/                # Configuration files
│   │   └── navigation.ts   # Sidebar & top navigation config
│   │
│   └── styles/
│       └── global.css      # Global styles & theme
│
├── public/                 # Static assets (images, icons)
└── package.json
```

---

## Writing Documentation Pages

### Creating a New Page

1. **Create a new `.mdx` file** in the `src/pages/docs/` folder
2. **Add frontmatter** at the top of the file
3. **Write your content** using Markdown
4. **Add to navigation** (see [Adding Pages to Navigation](#adding-pages-to-navigation))

### Example: Creating a New Page

Create a file at `src/pages/docs/my-new-page.mdx`:

```mdx
---
layout: ../../layouts/DocsLayout.astro
title: My New Page
description: A brief description of what this page covers.
---

## Introduction

Write your content here using Markdown.

### Subsection

More content...
```

### Frontmatter Reference

Every documentation page must start with frontmatter (the section between `---` markers):

| Field | Required | Description |
|-------|----------|-------------|
| `layout` | Yes | Always use `../../layouts/DocsLayout.astro` (adjust `../` based on folder depth) |
| `title` | Yes | Page title (shown in browser tab and page header) |
| `description` | No | Brief description (shown below title, used for SEO) |

### File Naming Rules

- Use **lowercase** letters
- Use **hyphens** for spaces (e.g., `getting-started.mdx`, not `Getting Started.mdx`)
- Use `.mdx` extension (allows using components in Markdown)
- The filename becomes the URL path:
  - `src/pages/docs/quickstart.mdx` → `/docs/quickstart`
  - `src/pages/docs/evaluate/metrics.mdx` → `/docs/evaluate/metrics`

### Creating Nested Sections

For sections with sub-pages (like `/docs/evaluate/`):

```
src/pages/docs/evaluate/
├── index.mdx       # Overview page at /docs/evaluate
├── metrics.mdx     # Sub-page at /docs/evaluate/metrics
├── custom.mdx      # Sub-page at /docs/evaluate/custom
└── datasets.mdx    # Sub-page at /docs/evaluate/datasets
```

---

## Adding Pages to Navigation

### Sidebar Navigation

Edit `src/lib/navigation.ts` to add pages to the sidebar:

```typescript
export const navigation: NavSection[] = [
  {
    title: 'Getting Started',      // Section header
    icon: 'book',                  // Icon name (see icon list below)
    items: [
      { title: 'Introduction', href: '/docs/introduction' },
      { title: 'Quickstart', href: '/docs/quickstart', badge: '5 min' },
      { title: 'Installation', href: '/docs/installation' },
      // Add your new page here:
      { title: 'My New Page', href: '/docs/my-new-page' },
    ]
  },
  // ... more sections
];
```

#### Navigation Item Options

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Display text in sidebar |
| `href` | Yes | URL path to the page |
| `badge` | No | Small label (e.g., "New", "5 min", "Beta") |

#### Available Section Icons

Use these icon names for section headers:

- `book` - Getting started, guides
- `check-circle` - Evaluation, testing
- `activity` - Monitoring, observability
- `trending-up` - Optimization, performance
- `shield` - Security, protection
- `play-circle` - Simulation, demos
- `puzzle` - Integrations
- `code` - API, SDK reference
- `file` - General documentation

### Top Navigation Bar

Edit the `topNav` array in `src/lib/navigation.ts`:

```typescript
export const topNav = [
  { title: 'Docs', href: '/' },
  { title: 'Cookbook', href: '/docs/cookbooks' },
  { title: 'Libraries', href: '/docs/integrations' },
  { title: 'Data API', href: '/docs/api' },
  { title: 'Changelog', href: '/changelog' },
  // Add new top-level sections here
];
```

---

## Using Components

MDX allows you to use React-like components in your Markdown. Import them at the top of your file.

### Callout / Alert Boxes

```mdx
---
layout: ../../layouts/DocsLayout.astro
title: Example Page
---
import Callout from '../../components/docs/Callout.astro';

## My Content

<Callout type="info">
  This is an informational note.
</Callout>

<Callout type="warning">
  Be careful about this!
</Callout>

<Callout type="error">
  This will cause problems if ignored.
</Callout>

<Callout type="success">
  Great job! You did it correctly.
</Callout>
```

**Callout Types:**
- `info` - Blue, for general information
- `warning` - Yellow, for cautions
- `error` - Red, for critical warnings
- `success` - Green, for confirmations

### Cards

```mdx
import Card from '../../components/docs/Card.astro';

<Card title="Getting Started" href="/docs/quickstart">
  Learn how to set up Future AGI in 5 minutes.
</Card>
```

### Code Groups (Tabbed Code Blocks)

```mdx
import CodeGroup from '../../components/docs/CodeGroup.astro';

<CodeGroup>
```python
# Python example
from futureagi import FutureAGI
client = FutureAGI()
```

```javascript
// JavaScript example
import { FutureAGI } from 'futureagi';
const client = new FutureAGI();
```
</CodeGroup>
```

### Prerequisites Box

```mdx
import Prerequisites from '../../components/docs/Prerequisites.astro';

<Prerequisites>
  - Python 3.8 or higher
  - An API key from the dashboard
  - Basic knowledge of REST APIs
</Prerequisites>
```

### TL;DR Summary

```mdx
import TLDR from '../../components/docs/TLDR.astro';

<TLDR>
  - Install with `pip install futureagi`
  - Set your API key
  - Call `client.evaluate()` to get started
</TLDR>
```

---

## Formatting & Markdown

### Basic Markdown Syntax

```markdown
# Heading 1 (don't use - page title handles this)
## Heading 2
### Heading 3
#### Heading 4

Regular paragraph text.

**Bold text**
*Italic text*
`inline code`

[Link text](https://example.com)

- Bullet list item
- Another item
  - Nested item

1. Numbered list
2. Second item

> Blockquote for callouts or quotes

---

Horizontal rule above
```

### Code Blocks

Use triple backticks with a language identifier:

````markdown
```python
def hello():
    print("Hello, world!")
```

```javascript
function hello() {
  console.log("Hello, world!");
}
```

```bash
pip install futureagi
```

```json
{
  "name": "example",
  "version": "1.0.0"
}
```
````

**Supported languages:** python, javascript, typescript, bash, json, yaml, sql, go, rust, java, and many more.

### Tables

```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Row 1    | Data     | More     |
| Row 2    | Data     | More     |
```

### API Endpoint Formatting

For REST API documentation, use this pattern:

```markdown
### Create Evaluation

<span class="http-method http-post">POST</span> `/api/v1/evaluations`

Creates a new evaluation for the given input/output pair.
```

---

## Images & Assets

### Adding Images

1. Place images in the `public/` folder:
   ```
   public/
   └── images/
       └── my-screenshot.png
   ```

2. Reference in Markdown:
   ```markdown
   ![Alt text description](/images/my-screenshot.png)
   ```

### Image Best Practices

- Use descriptive filenames: `evaluation-dashboard.png` not `screenshot1.png`
- Optimize images before adding (use tools like [TinyPNG](https://tinypng.com/))
- Provide meaningful alt text for accessibility
- Recommended formats: PNG for screenshots, SVG for diagrams, WebP for photos

---

## Running Locally

### Development Server

```bash
# Start the dev server with hot reload
npm run dev
```

The site will be available at http://localhost:4321

Changes to `.mdx` files will automatically refresh in the browser.

### Building for Production

```bash
# Create a production build
npm run build

# Preview the production build locally
npm run preview
```

---

## Common Tasks

### Task: Add a New Documentation Page

1. Create the file:
   ```bash
   touch src/pages/docs/my-new-feature.mdx
   ```

2. Add content:
   ```mdx
   ---
   layout: ../../layouts/DocsLayout.astro
   title: My New Feature
   description: Learn how to use the new feature.
   ---

   ## Overview

   Explain the feature here...
   ```

3. Add to sidebar navigation in `src/lib/navigation.ts`:
   ```typescript
   {
     title: 'Getting Started',
     icon: 'book',
     items: [
       // ... existing items
       { title: 'My New Feature', href: '/docs/my-new-feature' },
     ]
   }
   ```

4. Test locally: `npm run dev`

### Task: Add a New Section to Sidebar

1. Add a new section object in `src/lib/navigation.ts`:
   ```typescript
   {
     title: 'New Section',
     icon: 'puzzle',  // Choose an icon
     items: [
       { title: 'Overview', href: '/docs/new-section' },
       { title: 'First Topic', href: '/docs/new-section/first-topic' },
     ]
   }
   ```

2. Create the corresponding pages:
   ```bash
   mkdir -p src/pages/docs/new-section
   touch src/pages/docs/new-section/index.mdx
   touch src/pages/docs/new-section/first-topic.mdx
   ```

### Task: Update the Changelog

Edit `src/pages/changelog.astro` or create entries following the existing pattern.

### Task: Add a Badge to a Nav Item

```typescript
{ title: 'New Feature', href: '/docs/new-feature', badge: 'New' }
{ title: 'Quick Start', href: '/docs/quickstart', badge: '5 min' }
{ title: 'Experimental', href: '/docs/experimental', badge: 'Beta' }
```

---

## Troubleshooting

### Page Not Showing in Browser

1. Check the file is in `src/pages/docs/`
2. Verify the filename uses `.mdx` extension
3. Ensure frontmatter has correct `layout` path
4. Check for typos in the URL

### Page Not in Sidebar

1. Verify you added the item to `src/lib/navigation.ts`
2. Check the `href` matches the file path exactly
3. Restart the dev server: `npm run dev`

### Component Not Rendering

1. Check the import path is correct (count the `../` properly)
2. Ensure you're using `.mdx` not `.md` extension
3. Component names are case-sensitive

### Layout Path Issues

The layout path depends on your file's location:

| File Location | Layout Path |
|--------------|-------------|
| `src/pages/docs/page.mdx` | `../../layouts/DocsLayout.astro` |
| `src/pages/docs/section/page.mdx` | `../../../layouts/DocsLayout.astro` |
| `src/pages/docs/section/sub/page.mdx` | `../../../../layouts/DocsLayout.astro` |

### Build Errors

```bash
# Clear cache and rebuild
rm -rf node_modules/.astro
npm run build
```

---

## Style Guide

### Writing Tips

1. **Be concise** - Get to the point quickly
2. **Use active voice** - "Run the command" not "The command should be run"
3. **Start with the goal** - Tell readers what they'll achieve
4. **Use examples** - Show, don't just tell
5. **Keep paragraphs short** - 2-3 sentences max

### Heading Guidelines

- Use **H2** (`##`) for main sections
- Use **H3** (`###`) for subsections
- Use **H4** (`####`) sparingly for sub-subsections
- Don't skip levels (don't go from H2 to H4)
- Keep headings short and descriptive

### Code Example Guidelines

- Always specify the language for syntax highlighting
- Keep examples minimal and focused
- Include comments for complex code
- Show expected output when helpful

---

## Getting Help

- **Questions?** Open an issue in the repository
- **Found a bug?** Report it with steps to reproduce
- **Suggestions?** We welcome pull requests!

---

## Quick Reference

### New Page Checklist

- [ ] Created `.mdx` file in correct location
- [ ] Added frontmatter with layout, title, description
- [ ] Added to `navigation.ts`
- [ ] Tested locally with `npm run dev`
- [ ] Checked all links work
- [ ] Reviewed for typos

### File Paths Quick Reference

| What | Where |
|------|-------|
| Documentation pages | `src/pages/docs/*.mdx` |
| Navigation config | `src/lib/navigation.ts` |
| Components | `src/components/docs/*.astro` |
| Images | `public/images/*` |
| Global styles | `src/styles/global.css` |
