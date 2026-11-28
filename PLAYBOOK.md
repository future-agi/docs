# Future AGI Docs Playbook

Start with the reader’s question. Show the evidence that answers it, then link to what they can do next.

This playbook says how every docs page is written and how every existing page is audited. It is built from the pilot page Nikhil approved, his review notes, and pages from Langfuse, LangSmith and other docs teams.

## The bar

- **Model page:** `src/pages/docs/cookbook/quickstart/conversation-eval.mdx` on the docs#1150 branch, titled “Check booking claims with Write with AI”. Read the file before you write. Until #1150 ships, the public URL for that route still serves the older “Multi-Turn Conversation Eval” page.
- **Why it passed:** it opens with the problem and what you will build, shows the flow, puts a narrated recording of a real run at the top, uses short one-action steps with cropped screenshots, shows real outputs, covers every surface that exists, and links the concepts it mentions.
- **Review gate:** a cookbook, or any page built around a UI workflow, goes to Nikhil only when it has all four: a narrated video of a real run, a flow diagram, a step-by-step tutorial, and real examples. A text-only or navigation-only change is not reviewable work.

## Non-negotiables

- Use plain English, short paragraphs, descriptive headings, and active voice. Do not use em-dashes.
- Say **credits**, never “AI credits”. Never use “cheap”.
- Name the CLI **`fagi`**. Name the self-improvement product **Epoch**. Use **Agent Learning Kit**, never `ai-evaluation`.
- Simulation means environments. There is no “Simulation SDK” story: simulation pages are driven by RL environments and live under **Environments and Simulations**. Epoch has its own tab. Do not imply that Epoch updates model weights.
- Prefer one canonical page for one job. Link to a sibling page instead of repeating its full instructions.
- Do not claim a surface, command, output, or integration until it has been run on the build being documented (the next release; see item 1 in `../research/ANSWERS.md`). A missing surface gets one honest sentence, not an invented tab.
- Every code block must run as written. Tests use OpenRouter; public pages show OpenAI where the product or example calls for it.
- Use real, safe, redacted runs. Never fabricate screenshots, results, names, IDs, or performance numbers. An output that did not come from a real run does not go on the page.
- The FAQ is parked. Do not edit or audit it until Nikhil reopens it.

## Reference patterns studied

Each page below was opened on 28 Nov 2026. The notes say only what the page itself shows. More patterns are in `../research/lane-competitor-media.md` and `../research/lane-competitor-usecases.md`.

| Page type | References and what to copy |
| --- | --- |
| Cookbook or use case | [LangSmith: Evaluate a RAG application](https://docs.langchain.com/langsmith/evaluate-rag-tutorial) builds one app, names what each evaluator compares in its heading (“Groundedness: Response vs retrieved docs”), shows Python and TypeScript, and ends with the full reference code. [Langfuse: Evaluating Multi-Turn Conversations](https://langfuse.com/guides/cookbook/example_evaluating_multi_turn_conversations) runs six numbered steps from a traced chat app to a dataset, a scorer, and a second run after the fix. [Phoenix: Session-level Evaluation](https://arize.com/docs/phoenix/cookbook/evaluation/session-level-evaluation) scores the whole conversation instead of single turns and has a section on what session-level evals catch. [Supabase: Use Supabase with Next.js](https://supabase.com/docs/guides/getting-started/quickstarts/nextjs) uses numbered one-job steps, gives environment variables their own step, and closes with “Start the app”, production requirements and “Next steps”. |
| Feature guide | [Langfuse: LLM-as-a-Judge](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge) includes a short product video, a decision tree, “Set up step-by-step”, an exact error string as a heading, and a debugging section. [LangSmith: Set up LLM-as-a-judge online evaluators](https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge) gives every option its own heading: filter, sampling rate, past runs, spend limit. [LangSmith: Set up multi-turn online evaluators](https://docs.langchain.com/langsmith/online-evaluations-multi-turn) runs How it works, Prerequisites, Configuration, Limits, Troubleshooting. [Stripe: Manage products and prices](https://docs.stripe.com/products-prices/manage-prices) has one heading per operation (create, edit, archive, delete) and covers the Dashboard and the API. |
| Concept page | [Langfuse: Core Concepts](https://langfuse.com/docs/evaluation/core-concepts) starts with the evaluation loop, gives each term its own heading, and has a “How these work together” section. [LangSmith: Evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts) ends with a quick reference that compares offline and online evaluation. [LangSmith: Application-specific evaluation approaches](https://docs.langchain.com/langsmith/evaluation-approaches) is organised by application type, and its RAG section by the choice the reader has to make: dataset, evaluators, evaluation mode. [Supabase: RAG with Permissions](https://supabase.com/docs/guides/ai/rag-with-permissions) teaches with one worked example, then alternative scenarios. |
| Integration page | [Langfuse: LangChain integration](https://langfuse.com/integrations/frameworks/langchain) runs install, initialize, example, then “See Traces in Langfuse”, in Python and JS/TS, followed by extra configuration and upgrade paths. [LangSmith: Trace with the OpenAI Agents SDK](https://docs.langchain.com/langsmith/trace-with-openai-agents-sdk) runs Installation, Environment configuration, Quick start, then processor settings and flushing in serverless environments. |
| API or SDK reference | [Stripe API reference](https://docs.stripe.com/api) puts authentication and errors first. [Braintrust API reference](https://docs.braintrust.dev/api-reference) runs Base URL, Authentication, SDKs, API resources, Response format, Rate limits, then task sections. [Supabase JavaScript reference](https://supabase.com/docs/reference/javascript/introduction) runs Installing, Initializing, then one heading per method with a Parameters block. |
| Overview or landing | [Vercel: Deployments](https://vercel.com/docs/deployments) lists every way to do the job (Git, CLI, deploy hooks, REST API), then where to manage the result. [Langfuse: Guides](https://langfuse.com/guides) groups its index into introduction, evaluation tutorials, cookbooks and video tutorials. [Arize AX: Guides](https://arize.com/docs/ax/cookbooks) groups its guides as Instrument, Observe, Evaluate, Improve. |
| Troubleshooting | [Vercel: Troubleshooting build errors](https://vercel.com/docs/deployments/troubleshoot-a-build) starts with where to look, then gives each symptom its own heading (“Build logs keep loading”). [LangSmith: Troubleshooting](https://docs.langchain.com/langsmith/troubleshooting) opens with “Getting helpful information”, then uses exact error strings as headings (“413 - request entity too large”). [Langfuse: missing traces](https://langfuse.com/faq/all/missing-traces) is titled with the reader’s symptom: “I do not see any traces in Langfuse”. |

## Page types and skeletons

Set `page-type` in the frontmatter to one of: `cookbook`, `feature-guide`, `concept`, `integration`, `api-reference`, `overview`, `troubleshooting`. Use the sections in order.

| Where the page lives | Type |
| --- | --- |
| `cookbook/**`, product `quickstart` pages, `get-started/*` | Cookbook. Quickstarts use the same skeleton, shorter. |
| `*/guides/**`, `*/features/**` | Feature guide |
| `*/concepts/**` | Concept |
| `integrations/**`, `get-started/migrate/**`, `sdk/tracing/langfuse-integration` | Integration |
| `api/**`, `sdk/**` (except the integration page above), `*/reference/**` | API or SDK reference |
| Section `index` pages, `cookbook/use-cases/index` | Overview or landing |
| `*/troubleshooting*` | Troubleshooting |
| `faq`, `release-notes` | Not scored. The FAQ is parked. Release notes get link and terminology checks only. |

### 1. Cookbook or use case: problem-led tutorial

**Required order:**

1. Frontmatter. Copy the pilot’s keys: `title`, `slug`, `description`, `date`, `author`, `products`, `frameworks`, `difficulty`, `time-to-complete`, `tags`, `canonical`, `page-type`.
2. `<TLDR>` with one sentence on what the reader builds.
3. The narrated demo video.
4. The transcript, collapsed in `<details>`.
5. **The problem**: who is affected, what goes wrong, and why the usual checks miss it.
6. **What you’ll build**: one sentence, then the Mermaid flow.
7. Outcome list: “You’ll:” and three to five numbered outcomes.
8. **Before you start**, in `<Prerequisites title="Before you start">`.
9. The UI walkthrough: one H2 per stage, one-action steps, cropped screenshots.
10. Real output and how to read it.
11. **Run from code**: the env var table, then tabs for each code surface that exists.
12. One sentence for each surface that does not exist yet.
13. **Trace your own agent**, or the equivalent section that lets readers produce their own data.
14. **Run on new conversations**, or the equivalent handoff to production.
15. **Troubleshooting**.
16. **Next**.

Keep the page to 1,500 to 3,000 words, excluding the transcript and code. **Optional:** decision table, downloadable fixture, known limitations.

Body template, taken from the pilot. Replace `PAGE` with the slug:

````mdx
<TLDR>
**What you'll build:** One sentence with the result and the failure it catches.
</TLDR>

<video controls preload="metadata" poster="/images/docs/cookbook/PAGE/poster.png" width="1920" height="1200" style={{ width: "100%", height: "auto", borderRadius: "5px" }}>
  <source src="/videos/docs/cookbook/PAGE/demo.mp4" type="video/mp4" />
  <track kind="captions" src="/videos/docs/cookbook/PAGE/demo.vtt" srclang="en" label="English" default />
  Your browser does not support the video tag.
</video>

<details>
<summary>Read the video transcript</summary>

The full narration, one paragraph per scene.

</details>

## The problem

Who is affected, what goes wrong, and why the usual checks miss it.

## What you'll build

One sentence that states the result.

<Mermaid chart={`
flowchart LR
    accTitle: Short title of the flow
    accDescr: One or two sentences that describe the flow in words.
    A["Input"] --> B["Agent"]
    B --> C["Evidence"]
    C --> D["Check"]
    D --> E["Result"]
`} />

You'll:

1. First outcome.
2. Second outcome.

<Prerequisites title="Before you start">
- What the reader needs, linked to the page that explains how to get it.
</Prerequisites>

## Name the stage with a verb

1. One action, with the exact **UI label**.
2. One action.

   What the reader should now see.

![What the screenshot shows and what changed.](/images/docs/cookbook/PAGE/01-name.png)

## Run from code

<div class="sdk-ref-table max-sm:[&_td]:px-1.5! max-sm:[&_th]:px-1.5!">

| Variable | What to set | Where to find it |
| --- | --- | --- |
| `FI_API_KEY` | Workspace API key | **Build > Keys** |

</div>

<Tabs>
<Tab title="Python">

Install line with exact versions, the file name, the run command, the code, then the real output.

</Tab>
<Tab title="TypeScript">

The same job with the same output shape.

</Tab>
</Tabs>

One sentence for each surface that does not exist yet.

## Trace your own agent

## Run on new conversations

## Troubleshooting

- **Symptom in the reader's words.** What to check, then the fix.

## Next

- [Page title](/docs/route): why to go there next.
````

### 2. Feature guide: do one thing in the product

**Required order:** outcome and when to use it; prerequisites; a decision or scope note; numbered UI procedure; the same job on each code surface that exists; expected result; every option on the screen; limits and permissions; troubleshooting; related concepts; **Next**.

Use exact labels such as **Build > Evals > Create evals**. Before the steps, name the choices that change the result. Cover every option the screen offers, in a table if there are many: for an Observe eval that means data unit, dates, filters, sampling, debugging and editing. Keep it detailed but simple: one option per row, one sentence each. Afterward, show where to inspect a result and edit the rule. Aim for 800 to 1,800 words. **Optional:** migration or audit history.

### 3. Concept page: build a mental model

**Required order:** one-sentence definition; why it matters; running example; diagram or data model when it clarifies relationships; definitions table; what it includes and does not include; comparison or decision table; links to the task guides and cookbooks that use it; **Next**.

Aim for 700 to 1,500 words. Example: explain sessions, traces and spans with one booking conversation, then link to `/docs/observe/guides/setup-evals`. **Optional:** glossary or counterexample.

### 4. Integration page: connect two systems

**Required order:** integration outcome; architecture and trust boundary; supported versions; prerequisites and credentials; setup; one end-to-end verification; failure modes; security and data handling; surface matrix; **Next**.

Show where data lives and whose permissions apply. Identify the same event on both sides: send a known input, then find its trace in the destination project. Aim for 1,000 to 2,000 words. **Optional:** provider matrix, webhook replay, migration path, or cost and retention note.

### 5. API or SDK reference: find and call an operation

**Required order:** scope and audience; base URL and auth; version and compatibility; installation; resource or method index; parameter and return tables; minimal runnable examples; errors and pagination; links to related guides; **Next**.

Use the released signature as the lookup key. Link setup rather than repeating it on each method page. Put field type, units, default and required status beside the field. Aim for 500 to 1,500 words per index or 300 to 1,000 per method. **Optional:** changelog, deprecations, pagination recipe, examples repository, or SDK parity table.

### 6. Overview or landing page: route by intent

**Required order:** product promise; audience and outcome; visual or lifecycle model; intent-to-page table; supported surfaces; key concepts; featured guides; limits or boundaries; **Next**.

Group links by decision, not department. “Test a booking claim before release” and “Check new conversations as they arrive” lead to different destinations. On the use-case index, each card states the problem and what the reader builds, and every card leads to a page that meets the cookbook bar. The docs home uses the line “Future AGI is the infrastructure for self-improving AI agents.” Aim for 500 to 1,200 words. **Optional:** comparison matrix, release note, or featured video.

### 7. Troubleshooting: symptom to evidence to fix

**Required order:** scope; quick checks; a symptom table; one section per exact error or observed symptom; evidence to collect; fix; verification; escalation and support links; **Next**.

Use searchable error headings. Distinguish missing permissions from the wrong data shape: each needs a different fix. Aim for 600 to 1,800 words. **Optional:** known incidents, diagnostic bundle template, or support escalation checklist.

## Content rules

### Opening and flow

- Open with a concrete failure, not a feature claim. Instead of “Evaluate agent quality at scale”, write “The assistant said ‘reserved’. The tool returned `pending_payment`. Build a check that fails when those disagree.”
- In a cookbook, the first two headings are **The problem** and **What you’ll build**. The video sits above them, directly under the TL;DR.
- Use one running example for the whole page. The pilot follows two guests, Maya and Daniel, from the video to the last code output.
- Draw the flow with the repository’s `<Mermaid>` component, not a screenshot of a diagram. Include `accTitle` and `accDescr`. Keep it to the steps the reader needs.

### Demo video

A narrated video is required for a cookbook, a multi-surface workflow, or a UI flow whose result is central to the story. It is optional for a concept, an API reference, or a small troubleshooting fix.

- Record a real run with safe, reproducible data.
- Aim for 60 to 100 seconds. The pilot is 99 seconds at 1920×1200. Set `width` and `height` to the real frame size.
- Narrate in the first person and stay calm. Open with “Hi” and one sentence on what the viewer will see. The transcript in the pilot is the model.
- Use Nikhil’s approved voice with the settings in item 4 of `../research/ANSWERS.md`. Do not put an “AI voice” label on the video or the page (his decision of 27 Nov). Never clone anyone else’s voice without their permission.
- Zooms ease in to the area that matters, hold, then ease back out. No hard cuts, no jumpy cursor, no unexplained loading. Do not zoom in so far that the viewer loses where the control sits.
- Include `controls`, a `poster` taken from the video, a captions track marked `default`, and the full transcript in `<details>`.

### Screenshots

- Crop to the relevant control and its result. Show the state after the action, and the state before it when the change is the point.
- Use real data with secrets and personal data removed.
- Never use numbered-dot callouts. Use a clean crop and alt text that states the visible action and outcome, such as “Session context enabled in the Data Injection menu; the footer now shows one context.”
- Put the screenshot directly under the step it proves.

### Steps and checkpoints

- One numbered step is one user action. Put the explanation, warning, or expected state in an indented paragraph under the step.
- Name each stage with a verb (“Write the rule”, “Test on two sessions”). Keep a stage to about eight steps.
- End each group of steps with a checkpoint: what the reader should now see, such as “The footer should now show **+1 context**.”
- After the main procedure, show the real result as a table, JSON response, trace, score, or screenshot. Say what proves success and what a failure looks like. The pilot runs one passing and one failing session through the same rule.
- Show the output the run produced, even when it is imperfect. The pilot says that one Python run passed Maya without citing her confirmation number.

### Code, env vars and outputs

- Put an env var table before the code: variable, what to set, where to find it. Mark self-hosted-only variables. Do not put secrets in code or screenshots.
- Name the runtime version, the file name, and the run command (“Save as `check.py` and run `python check.py`”).
- Pin every Future AGI package to the latest released version, checked against the registry on the day you ran it, as the pilot does (`futureagi==0.8.1`, `@future-agi/sdk@0.3.1`). A third-party client such as `openai` may stay unpinned if the run evidence records the version that ran.
- Use each SDK for the job it owns: Agent Learning Kit for evals, optimization, simulation and the harness; the `futureagi` platform SDK for datasets, prompts, knowledge bases, eval tasks and annotation. This split is a working reading (item 6 in `../research/ANSWERS.md`); check the released packages before you rely on it.
- Run each tab from scratch on a disposable cloud runner. Attach redacted logs, versions and fixture links to the PR. Keep install commands, imports, APIs, and outputs consistent across tabs.
- Tests use OpenRouter even when the public page shows OpenAI. Keep the provider override outside the public script. Record which path ran: a proxy test does not verify OpenAI credentials or provider-specific behavior.
- Collapse long outputs in `<details>` with a summary that says what is inside.

### Surfaces

- Show the UI first, the way the video does. Then show each code surface that exists: Python, TypeScript, `fagi`, MCP.
- Use tabs only for supported surfaces. Do not show a guessed command, a placeholder endpoint, or a tab that only repeats another surface.
- If a surface is absent, say so in one sentence, as the pilot does: “The `fagi` CLI and MCP do not take a session ID for this eval yet.”

### Cross-linking and navigation

If a reader could want to know more about a term, link it.

- Link the first mention of every concept, product, integration, evaluator, API object, surface, and prerequisite that has its own page. Link the noun, not “click here”.
- Scope: body prose, tables, captions, step notes and troubleshooting items. Bold UI labels inside a step and the video transcript are not links. Link the term in the sentence that explains the step instead.
- Write links root-relative, such as `/docs/observe/concepts/sessions`. Do not hard-code the docs domain.
- Link both ways. A concept page links to the cookbooks and guides that use it, and each cookbook links back to the concept.
- From a tutorial, link to the relevant concept, feature guide, reference, integration, and troubleshooting page.
- End every page with **Next**: three to five links, each with a one-line reason. Always include the immediate follow-on task and one deeper concept. Add the production path, the reference, Environments or Epoch where they fit.
- Link simulation to `/docs/environments`. Link failures that can be fixed to `/docs/epoch`. Describe how an Epoch session opens as the build behaves; do not write “opens in a new tab” unless the run showed it.
- If a term has no page, record the gap. Never guess a URL.
- Run `npm run audit-links -- --verbose` in cloud validation. It checks paths and lists orphan pages; it does not check fragments, so open anchors, downloads and topic links in the preview. A green link check cannot detect an unlinked concept.

**Link map.** Every route below exists on the docs#1150 branch.

| When you mention | Link to |
| --- | --- |
| session, trace, span, user | `/docs/observe/concepts/sessions`, `/docs/observe/concepts/traces`, `/docs/observe/concepts/spans`, `/docs/observe/concepts/users` |
| Observe; evals on live traffic, filters, sampling | `/docs/observe`; `/docs/observe/guides/setup-evals` |
| Evaluation; eval types (Agents, LLM-as-Judge, Code) | `/docs/evaluation`; `/docs/evaluation/concepts/eval-types` |
| evaluator models (Turing); eval templates; built-in evals | `/docs/evaluation/concepts/evaluator-models`; `/docs/evaluation/concepts/eval-templates`; `/docs/evaluation/builtin` |
| Test Evaluation | `/docs/evaluation/guides/explore-playground/test-an-eval` |
| Environments and Simulations; reading a run | `/docs/environments`; `/docs/environments/guides/read-run-results` |
| Epoch; run one; review one | `/docs/epoch`; `/docs/epoch/run-an-epoch`; `/docs/epoch/review-an-epoch` |
| Error Feed; Knowledge Base; datasets; prompts; optimization; Protect | `/docs/error-feed`; `/docs/knowledge-base`; `/docs/dataset`; `/docs/prompt`; `/docs/optimization`; `/docs/protect` |
| SDKs; SDK reference; session and user helpers | `/docs/sdk`; `/docs/sdk/reference`; `/docs/sdk/tracing/context-helpers` |
| traceAI; tracing OpenAI | `/docs/integrations/traceai`; `/docs/integrations/traceai/openai` |
| API key and secret key | `/docs/admin-settings/api-keys` |
| MCP server | `/docs/falcon-ai/guides/use-the-mcp-server` |
| credits and billing; self-hosting; REST API | `/docs/billing`; `/docs/self-hosting`; `/docs/api` |
| Langfuse (our pages) | `/docs/integrations/import/langfuse`; `/docs/get-started/migrate/langfuse`; `/docs/sdk/tracing/langfuse-integration` |
| LangSmith (our page) | `/docs/integrations/langsmith` |

Known gaps, with no page to link to yet: the `fagi` CLI, Write with AI, and Session context.

### Formatting

- Bold exact UI labels and menu paths: **Build > Evals > Create evals**. Use backticks for values, variables, file names and IDs.
- One idea per paragraph. Three sentences is a long paragraph.
- Use the repository components: `<TLDR>`, `<Prerequisites>`, `<Tabs>` and `<Tab>`, `<Mermaid>`, `<details>`.
- Wrap wide tables in the `sdk-ref-table` div, as the pilot does, so they stay readable on a phone.
- Use tables for comparisons and settings, numbered lists for actions, and bullets for everything else.

### Voice, terminology and SEO

- Prefer “You will compare two sessions” to “We will be exploring”. Explain acronyms on first use.
- Use the words people search for, naturally, from `../research/lane-keywords.md`: **LLM evals**, **LLM-as-a-judge**, **evaluate a multi-turn conversation**, **full conversation history**, **pass/fail**, **agent testing in RL environments**, **run online evals on production traces**, **debug agent traces**, **voice agent testing**, **build a RAG knowledge base**, and **Epoch: self-improving agents**. Choose one primary phrase per page.
- Title: name the task or outcome in up to about 60 characters. The pilot’s is 39.
- Description: one or two sentences that state the outcome, about 120 to 170 characters. No keyword lists.

### Accessibility

Use semantic heading order, descriptive link text, keyboard-accessible tabs, visible focus, captions, a transcript, and meaningful alt text. Do not rely on color alone for Pass or Fail, improvements, or regressions. Give tables header cells and a mobile-safe layout. Mermaid diagrams need a title and description. Check the page at narrow width and with the video muted.

## Audit every page

Nikhil’s ask is to go through all the other pages and make sure they follow this playbook. That covers every route, not only the sidebar.

1. **Inventory.** List every file under `src/pages/docs`. There are about 850 on the docs#1150 branch. `npm run audit-links -- --verbose` also lists pages that are missing from the navigation.
2. **Type.** Give each page a type from the table above and set `page-type`. Only 68 pages have it today, all of them cookbooks.
3. **Score.** Use [rubric.json](rubric.json). Write one record per page in its `audit_record` shape, saved as `audit-<section>.json` beside this file. Summarise in `AUDIT.md`.
4. **List the links.** Walk each page against the link map and record every unlinked term with its target.
5. **Fix in this order:** the pages Nikhil named in `../research/FEEDBACK.md`; then cookbooks and quickstarts; then feature guides and integrations; then concepts and overviews; then reference and troubleshooting.
6. **Fix honestly.** Links, **Next**, the opening story, terminology and structure are text fixes. A video, a screenshot, or an output needs a real cloud run. Never add a placeholder video or an invented output to raise a score.
7. **Rescore** after the edits. A page is done when it passes and meets the review gate for its type.

“Langfuse, LangSmith, etc.” in his ask can mean two things, so do both. Their docs are the references in the table above. Our own pages about them are integration pages and go in the first integration batch: `/docs/integrations/langsmith`, `/docs/integrations/import/langfuse`, `/docs/get-started/migrate/langfuse` and `/docs/sdk/tracing/langfuse-integration`.

## Audit rubric

Use [rubric.json](rubric.json). It holds the full level text, the checks, what media each page type needs, and two scored example pages.

- Score each criterion 0, 1 or 2. Every criterion counts the same.
- Score a criterion for every page type it always applies to. Where it applies only if the element is present, record N/A with a reason. Never use N/A for missing required work.
- Absence never earns a 2. A page with no media does not get full marks for accessibility.
- Pass at 75% of available points (points earned divided by twice the number of applicable criteria), with no zero on purpose and story, media and evidence, code, cross-linking or accessibility, and with the review gate met.
- Below 50% the verdict is rewrite. Between 50% and a pass it is fix.

| Criterion | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Purpose and story | No user problem or outcome | Topic is named but the problem is thin | Problem, cost, and result are clear at once |
| Required structure | Type unclear, or most required sections missing | Some sections missing or out of order | Full skeleton, in order, easy to scan |
| Media and evidence | Required media missing, or evidence is illustrative | Real, but something required is incomplete | Real artifacts; every required item present and complete |
| Actionable steps | No steps, or a step is a whole script | Mostly one action; checkpoints or labels missing | One action per step; each group ends with a checkpoint |
| Code quality and runnability | Untested or cannot run as written | Probably runs; no clean-run evidence or unpinned Future AGI package | Clean run, pinned Future AGI packages, real output shown |
| Surface parity | Invented surface, or one surface and silence on the rest | Several surfaces, but one that exists is missing or unstated | Every existing surface shown; each absent one named |
| Verification and output | No success condition, or invented output | Real result, but no proof or no failing case | Reader can compare expected and actual, pass and fail |
| Cross-linking | Mostly unlinked, or broken links | Some first mentions unlinked, or weak **Next** | Every first mention linked; **Next** has three to five reasons |
| Voice and terminology | A naming rule is broken | Jargon, passive voice or em-dashes | Plain English and exact product terms throughout |
| SEO and findability | Task cannot be identified | Bare feature name or generic description | Task in the title, outcome in the description, one search phrase |
| Accessibility | Content depends on media with no text equivalent | Partial, or required media missing | Every medium has its text equivalent; works by keyboard and on a phone |
| Troubleshooting and next decisions | No recovery path and no handoff | Only one of the two is useful | Specific next tasks; symptoms lead to check, fix, confirm |

Calibration, scored on 28 Nov 2026:

| Page | Score | Verdict |
| --- | --- | --- |
| Pilot, `cookbook/quickstart/conversation-eval.mdx` | 23 of 24 (96%) | Pass. One point lost on cross-linking. |
| Code-only cookbook, `cookbook/text-to-sql.mdx` | 8 of 24 (33%) | Rewrite. All four review gates missed. |

## PR checklist

Paste into the PR:

- [ ] I named the page type, set `page-type`, and followed its required skeleton.
- [ ] The opening states the problem and what the reader will build or decide.
- [ ] A cookbook has the flow diagram under **What you’ll build**.
- [ ] The demo, screenshots, outputs, and data come from a real safe run.
- [ ] The video has controls, a poster, captions, and a transcript, where required. It has no “AI voice” label.
- [ ] Every step is one action, and every group of steps ends with a checkpoint.
- [ ] Every code block runs as written. Future AGI packages are pinned to the latest release, and the run log is attached.
- [ ] The env var table says what to set and where to find it.
- [ ] Tabs show only verified UI, Python, TypeScript, `fagi`, or MCP surfaces, and each absent surface has one sentence.
- [ ] I linked every term that has a page on first mention, checked the page against the link map, and added **Next** with three to five reasons.
- [ ] I used credits, `fagi`, Epoch, and Agent Learning Kit correctly, with no em-dashes.
- [ ] SEO title, description, heading order, alt text, captions, and keyboard behavior are checked.
- [ ] I tested narrow-width rendering and ran `npm run audit-links -- --verbose`.
- [ ] Troubleshooting names likely symptoms and points to evidence before fixes.
- [ ] I scored the page with `rubric.json` and it passes, with the review gate met.

## Review notes

Independent review, 28 Nov 2026. Both files were edited in place.

**Checked**

- Read the pilot in full, Nikhil’s review notes, the answers file, and the media and keyword research. The use-case research file was searched for its URLs and the Langfuse, LangSmith, Braintrust and Arize rows, not read end to end.
- Opened all 23 reference URLs in the table above. All returned 200, and each site returns 404 for a made-up path. The notes beside each link come from the page’s own headings, with four exceptions that rest on word counts or tags in the page source: Python and TypeScript on the LangSmith RAG tutorial, Python and JS/TS on the Langfuse LangChain page, Dashboard and API on the Stripe page, and the video on the Langfuse judge page. The Arize AX grouping was read from the sidebar of one of its guides.
- Checked every `/docs/...` route in this file against `src/pages/docs` on the docs#1150 branch.
- Measured the pilot: video 99 seconds at 1920×1200, title 39 characters, description 167, about 1,580 words outside code and collapsed blocks.

**Fixed**

- The model page was linked by its public URL, which still serves the old page, and `/docs/epoch` returns 404 on the public site. Internal links are now routes, and the model is named by file.
- The integration row cited no integration pages, and the troubleshooting row cited a feature guide. Both now cite real pages of that type, with Langfuse and LangSmith in most rows.
- Removed claims about reference pages that could not be confirmed on the page, and dropped the Stripe Checkout quickstart because its content could not be read.
- Brought four rules in line with the pilot where the old numbers were not Nikhil’s: video length and frame size, title and description length, what **Next** must contain, and checkpoints per group of steps instead of per step.
- Added what was missing from his asks: the review gate, the cookbook template, the link map, the audit procedure, formatting rules, the voice and no-label decision, every-option depth for feature guides, and the environments and Epoch rules.
- The link checker command used pnpm. The repository uses npm.
- The rubric: see `review_notes` and `calibration` in `rubric.json`. The earlier version let a code-only page collect full marks for having nothing to fault.

**Pilot gaps found (the pilot is read-only here)**

- Four terms that have a page are unlinked at first mention: API key and secret key, Observe in the “You’ll” list, MCP, and self-hosted. Adding the links takes the pilot to 24 of 24.
- The tracing example installs `openai` without a version. The pin rule now allows that for third-party clients when the run evidence records the version.
- The clean-run ledger (`run3/pilot/ledger6.json`) covers the page as of commit f9d557c5. The six code blocks are byte-identical at the current head; later commits changed prose only.

**Open for Nikhil**

- Should third-party packages be pinned exactly as well? If yes, the pilot’s `openai` install and level 2 of the code criterion both change.
- The SDK ownership split in the code rules is a working reading, not confirmed.
- No page exists yet for the `fagi` CLI, Write with AI, or Session context, so those terms cannot be linked.
