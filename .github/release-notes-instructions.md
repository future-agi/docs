# Release-notes editorial instructions (customer-facing)

These instructions are read by the automated polish step in `changelog-sync.yml` and by any human
editing `src/pages/docs/release-notes.mdx`. The audience is **FutureAGI customers** — developers and
AI teams using the platform. Assume no knowledge of our internal codebase, tickets, or services.

## Your task
The mechanical importer (`scripts/changelog-from-release.mjs`) has just inserted a new
`## <version> (<date>)` section at the very top of `src/pages/docs/release-notes.mdx`, directly below
the `release-notes:insert-below` marker. Its bullets are raw conventional-commit subjects. **Rewrite
only that newest section** into customer-facing prose that matches the existing entries below it.

## Match the existing house style exactly
Look at the sections already on the page and mirror them:
- Bullets are `- **Benefit-led Title in Title Case:** one or two plain sentences.`
- Lead with what the user can now do or what now works — never the code mechanism.
- Phrase fixes as observed behavior, e.g. *"In some cases, X failed… This has been resolved."*
- Keep the existing MDX wrapper markup and the `Features` / `Bugs/Improvements` / `Breaking Changes`
  subsection headings (only include a subsection that has content).

## Cluster (the main job)
- Merge every bullet about the same feature or scope (e.g. all `model-hub:` / `simulate:` items) into
  **one** bullet led by the combined user benefit. Collapse exact duplicates (the same subject may
  appear twice from two commits — that is one bullet, not two).
- A dozen raw commits should become a handful of benefit statements.

## Drop or hide internal-only changes
- Drop changes a customer cannot observe: tests, CI, refactors, chores, dependency bumps, and
  internal-only performance/index work. If a change has a user-visible effect, keep it and describe
  the effect, not the mechanism.
- Never expose internal ticket IDs (e.g. `TH-7193`), internal service/module names (`tracer`,
  `fi-collector`), database/index/SQL details, or source file paths.

## Accuracy (critical — these are published to customers)
- Describe only what the source bullets state. **Never invent** API names, flags, endpoints, model
  IDs, or version numbers not present in the source. When unsure, omit rather than guess.
- Do not assert capabilities, limits, or guarantees the source does not state.

## Breaking changes
- Always in their own **Breaking Changes** subsection, each with a one-line migration note.

## Leave these aids in the file for the human reviewer
- If unsure how to phrase an item or which cluster it belongs to, keep the original bullet and append
  an inline `{/* REVIEW: ... */}` comment explaining the doubt.
- At the end of the section, add one `{/* SKIPPED: ... */}` comment listing what you dropped and why,
  so the reviewer can veto a drop.

## Hard constraints
- Edit **only** the newest `## <version>` section. Do not touch the marker, any older section, or any
  file other than `src/pages/docs/release-notes.mdx`.
- Preserve valid MDX: escape stray `<`, `{`, `}` in prose. Keep any commit/PR links from the source
  on the corresponding polished bullet where natural (the importer may strip them — do not fabricate).
- Leave your edits in the working tree; do not commit, push, or open a PR.
