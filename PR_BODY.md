## What

Rewrites `Roles & Permissions` into the self-serve RBAC reference, so customers stop asking us who can reach what.

Covers the organization/workspace split, all four organization roles and three workspace roles, annotation queue roles, multi-org membership, what is scoped to a workspace vs the organization, share links, both kinds of API key, invites and the invite ceiling, role changes and removal, seats and billing, and the two-factor policy. Ends with two permission tables and a 17-question FAQ.

Also aligns 13 sibling pages that contradicted it.

## Why

The page that existed described a system the code does not implement. Every claim here was re-derived from `future-agi/future-agi@origin/dev` (`2bf0d79b7`) by verifiers that read the source first and compared second, in two passes: once on the original page, then again on the replacement sentences.

118 claims checked. 66 were already grounded. 52 were wrong or imprecise and are corrected here.

The ones a customer would actually get burned by:

- **"The higher of the two roles wins" is false.** Two resolvers exist and disagree. The one guarding every write ignores your organization role entirely below Admin, so an organization Member added to a workspace as Workspace Viewer cannot create or edit there. The old page used that exact scenario as its worked FAQ example and got it backwards.
- **Remove and deactivate are the same operation.** There is one button. It soft-deactivates and keeps the record. The old page described two behaviours that do not exist.
- **The seat limit does not block invites.** The refusal path cannot fire, and the live invite endpoint has no seat logic at all. Extra seats bill as overage.
- **The 2FA policy is on Org Settings**, not the "Profile & Security" page, which does not exist. Members and Viewers cannot open Org Settings, so they never see the policy.
- **Sharing covers traces and Observe projects**, not the five resource types listed. Dashboards, datasets and eval runs have no share entry point.
- **Gateway request logs are invisible outside the default workspace**, the opposite of what the page claimed.
- **Workspace Admin leaks past organization-role gates.** The frontend collapses both roles into one string, so a Workspace Admin reaches Billing, Plans & Pricing and the Keys page regardless of their organization role. Documented rather than hidden.

## Diagram

Replaces the Mermaid flowchart with a hand-authored SVG built to the constants in #783. Every label was measured with `getBBox()` in a headless render; worst-case clearance is 35.5px horizontal.

## Screenshots

The three inherited screenshots were blurred. They now use the §7 masked convention: sharp black rect, white "masked" label.

Assets moved from the legacy `public/images/rbac/` to `public/images/docs/rbac/` per `WRITING_DOCS.md`, and terse markdown alt text replaced with descriptive sentences. `workspace-members.png` is removed, orphaned by the rewrite.

## Sibling pages

Thirteen contradictions with the corrected reference, all one or two lines:

| Page | Was | Now |
|---|---|---|
| `api-keys`, `admin-settings/index`, `faq`, `evaluation/troubleshooting` | API keys are Owner-only | Owner, Admin and Workspace Admin can open Keys; only an Owner can delete |
| `billing-pricing`, `admin-settings/index` | Billing is Owner and Admin only | Adds Workspace Admin, notes Cloud-only |
| `organization-settings` | 2FA locks members out immediately | Grace period, plus the self-2FA prerequisite the steps omitted |
| `user-management` | "Remove member ... revokes all access" | Marks them Deactivated, record kept |
| `user-management`, `workspace-management` | Printed `workspace_admin` / `workspace_member` / `workspace_viewer` | Real UI labels |
| `queues` | Only selected members can access a queue | Anyone in the workspace can browse it; only added members annotate |
| `self-hosting/user-management` | Pointed at a "Settings → Roles & Permissions" page | That page does not exist |
| 8 pages | Settings page names that do not match the sidebar | Members, Workspaces, Keys, Usage Summary, Plans & Pricing |

## Verification

- `node scripts/audit-links.mjs` — 0 broken content links, 0 broken nav links
- Every touched page renders 200 locally
- Page is registered in `src/lib/navigation.ts:696`
- No em dashes, no committed proof media, no ticket references in the diff

## Known gaps, deliberately left out

- **The invite email link expires at 3 days while the invite record lives 7.** Django's `default_token_generator` timeout is never overridden. Documenting it would enshrine a bug; it needs an engineering fix.
- **Per-seat overage pricing** is in the code but is an internal value, so it stays off a customer page.
- **Screenshot dimensions** are non-uniform (3346x1816, 1038x1362, 1038x1108) against the 3024x1964 house standard. These are pre-existing assets, not introduced here. A recapture needs a live logged-in session.
