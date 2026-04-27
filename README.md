<div align="center">

<a href="https://futureagi.com">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="Logo.png">
    <img alt="Future AGI" src="Logo.png" width="100%">
  </picture>
</a>

# Future AGI Documentation

The source for **[docs.futureagi.com](https://docs.futureagi.com)** — the developer and user documentation for [Future AGI](https://futureagi.com).

Built with [Astro](https://astro.build), MDX, React islands, and Tailwind CSS v4.

[**Read the docs →**](https://docs.futureagi.com)
&nbsp;·&nbsp;
[**Report an issue**](https://github.com/future-agi/docs/issues/new)
&nbsp;·&nbsp;
[**Open a PR**](https://github.com/future-agi/docs/pulls)

</div>

---

<div align="center">
  <img alt="Future AGI docs assistant in action" src="docs-assistant.gif" width="100%">
</div>

---

## Contributing

We welcome contributions from everyone — fixing a typo, clarifying a paragraph, adding a missing example, or writing a whole new page. Documentation is a team effort, and small improvements compound.

### Before you start

Please skim these — they save back-and-forth in review:

- **[CONTRIBUTING.md](./CONTRIBUTING.md)** — setup, workflow, and how to submit a PR. **Start here.**
- **[STYLE-GUIDE.md](./STYLE-GUIDE.md)** — voice, structure, and conventions. How we write.
- **[WRITING_DOCS.md](./WRITING_DOCS.md)** — deep reference: components, frontmatter, navigation, auto-injection.

### Ways to contribute

| If you want to… | Do this |
|---|---|
| Fix a typo or broken link | Open a PR directly — small fixes don't need prior discussion |
| Report a mistake or unclear section | [Open an issue](https://github.com/future-agi/docs/issues/new) with the page URL |
| Request a new guide or cookbook | [Open an issue](https://github.com/future-agi/docs/issues/new) describing the use case |
| Add a new page | Read [WRITING_DOCS.md](./WRITING_DOCS.md), then follow the flow in [CONTRIBUTING.md](./CONTRIBUTING.md) |
| Improve the site itself (styles, components, layout) | Open an issue first so we can discuss direction |

### Contribution workflow

```text
1. Fork the repo (external) or pull the latest `dev` (internal)
2. Create a branch:  git checkout -b docs/your-change
3. Make your changes, preview locally with `pnpm dev`
4. Check for broken links:  pnpm audit-links
5. Confirm the site builds:  pnpm build
6. Push and open a PR against `dev`
7. A maintainer reviews; once approved, changes flow `dev` → `main` → live site
```

Merging to `main` triggers an automated deploy to [docs.futureagi.com](https://docs.futureagi.com). Please don't push directly to `main` or `dev` — always go through a PR.

---

## Quick start (local setup)

**Prerequisites:** Node.js 18+ and `pnpm`.

```bash
# Clone
git clone https://github.com/future-agi/docs.git
cd docs

# Install
pnpm install

# Run dev server at http://localhost:4321
pnpm dev
```

### Create a new page

The scaffold script creates the MDX file and wires it into the sidebar in one step:

```bash
pnpm new-doc docs/evaluation/my-eval "My Custom Eval"
```

See [WRITING_DOCS.md](./WRITING_DOCS.md) for the full authoring reference — components, navigation, frontmatter, images, and common pitfalls.

### Commands

| Command | What it does |
|---|---|
| `pnpm dev` | Start dev server with hot reload |
| `pnpm build` | Production build + Pagefind search index |
| `pnpm preview` | Serve the production build locally |
| `pnpm new-doc <path> [title]` | Scaffold a new doc page |
| `pnpm audit-links` | Check for broken internal links |

---

## Project structure

```
docs/
├── src/
│   ├── components/docs/   # MDX components (Card, Tip, Tabs, Steps, ...)
│   ├── layouts/           # Page layouts
│   ├── lib/navigation.ts  # Sidebar & tab structure
│   ├── pages/docs/        # All doc pages (MDX) — file path maps to URL
│   ├── plugins/           # Vite plugin for auto-layout & auto-imports
│   └── styles/            # Global CSS and design tokens
├── public/images/docs/    # Images, organized by section
├── scripts/               # new-doc scaffold, link audit, etc.
└── .github/workflows/     # Deploy pipeline
```

---

## Writing rules at a glance

Full details live in [STYLE-GUIDE.md](./STYLE-GUIDE.md). Highlights:

- **Voice:** clear, direct, second person ("you"). No marketing fluff.
- **Headings:** start at `##` — the `<h1>` comes from frontmatter `title`.
- **Links:** relative paths (`/docs/...`), never hardcoded `https://docs.futureagi.com`.
- **Images:** place in `public/images/docs/<section>/`, reference as `/images/docs/...`.
- **Code blocks:** always language-tagged (```` ```python ````, ```` ```bash ````).
- **Examples over prose:** show a working snippet before explaining it.

---

## Branches

| Branch | Purpose |
|---|---|
| `main` | Production. Pushes here trigger a deploy. Protected — PR only. |
| `dev` | Integration. Open PRs against this. Protected — PR only. |
| `docs/*`, `fix/*`, `feat/*` | Feature branches — branch from `dev`, merge back to `dev`. |
| `main_archive`, `dev_archive` | Frozen snapshots of the pre-Astro docs site (kept for reference). |

---

## Reporting issues

Found something wrong, confusing, or missing? [Open an issue](https://github.com/future-agi/docs/issues/new) and include:

- The page URL (e.g. `https://docs.futureagi.com/docs/evaluation/overview`)
- What you expected vs. what the page says
- A suggested fix, if you have one

For security-sensitive issues, please email the team privately instead of opening a public issue.

---

## Getting help

- **Product questions:** [docs.futureagi.com](https://docs.futureagi.com) or the in-app chat
- **Contribution questions:** comment on your draft PR — we'll help
- **Anything else:** open an issue

Thanks for helping make Future AGI's docs better.
