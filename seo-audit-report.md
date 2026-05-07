# SEO Audit Report

Site: src/pages/docs/ | Files scanned: 612

---

## 1. Missing `description` — 0 files

_None — all files have descriptions._

## 2. Title too short (<15 chars) — 0 files

_None._

## 3. Title too long (>60 chars) — 1 files

- "Understanding Prototype: Pre-Production Testing in Future AGI" (61 chars) → src/pages/docs/prototype/concepts/understanding-prototype.mdx

## 4. Description too short (<120 chars) — 16 files

- (119 chars) "Access and manage your Future AGI API keys and secret keys from the developer da..." → src/pages/docs/admin-settings.mdx
- (116 chars) "Retrieve details of a specific call execution by UUID, including provider call I..." → src/pages/docs/api/call-executions/getcallexecutiondetails.mdx
- (106 chars) "List all custom eval configs, with optional filtering by project UUID or eval ta..." → src/pages/docs/api/custom-eval-configs/list-configs-filtered.mdx
- (115 chars) "Update an evaluation's config and key mapping, then optionally re-run it across ..." → src/pages/docs/api/dataset-evals/edit-and-run-eval.mdx
- (119 chars) "Trigger one or more evaluations to run across a dataset by submitting user eval ..." → src/pages/docs/api/dataset-evals/start-evals-process.mdx
- (112 chars) "Append a specified number of empty rows to an existing dataset by ID. Returns a ..." → src/pages/docs/api/datasets/add-empty-rows.mdx
- (118 chars) "Copy rows from a source dataset into a target dataset using a column mapping to ..." → src/pages/docs/api/datasets/add-rows-from-existing.mdx
- (118 chars) "Append rows to an existing dataset by uploading a CSV or JSONL file as multipart..." → src/pages/docs/api/datasets/add-rows-from-file.mdx
- (119 chars) "Add one or more columns to a dataset in a single request. Specify each column's ..." → src/pages/docs/api/datasets/columns/add-columns.mdx
- (113 chars) "Delete one or more rows from a dataset by row UUIDs, or delete all rows at once ..." → src/pages/docs/api/datasets/delete-rows.mdx
- (119 chars) "Create one or more copies of specific rows within a dataset by providing row UUI..." → src/pages/docs/api/datasets/duplicate-rows.mdx
- (116 chars) "Retrieve available models, tools, output formats, and tool choices for configuri..." → src/pages/docs/api/datasets/run-prompt/retrieve-run-prompt-options.mdx
- (113 chars) "Soft-delete a single eval task by UUID. The task must not be in running state. R..." → src/pages/docs/api/eval-tasks/delete-eval-task.mdx
- (119 chars) "Pause a running eval task by UUID. Task must be in running state. Returns a conf..." → src/pages/docs/api/eval-tasks/pause-eval-task.mdx
- (119 chars) "Find answers to frequently asked questions about Future AGI products, pricing, f..." → src/pages/docs/faq.mdx
- (119 chars) "Build a new prompt manually in the Prompt Workbench with full control over struc..." → src/pages/docs/prompt/features/create-from-scratch.mdx

## 5. Description too long (>155 chars) — 47 files

- (158 chars) "Create a new version of an agent definition. Accepts agent name, language, syste..." → src/pages/docs/api/agent-versions/createagentversion.mdx
- (156 chars) "Get the default annotation queue for a project, dataset, or agent definition, au..." → src/pages/docs/api/annotations/queues/get-or-create-default.mdx
- (157 chars) "Transition an annotation queue to a new status (draft, active, paused, or comple..." → src/pages/docs/api/annotations/queues/update-status.mdx
- (162 chars) "Create an eval task for a project. Set eval configs, sampling rate, run type (co..." → src/pages/docs/api/eval-tasks/create-eval-task.mdx
- (161 chars) "Create a workspace-level persona for voice or text simulation. Set gender, age g..." → src/pages/docs/api/personas/createpersona.mdx
- (170 chars) "List system and workspace personas with pagination. Filter by type (prebuilt/cus..." → src/pages/docs/api/personas/listpersonas.mdx
- (182 chars) "Add one or more evaluation configurations to an existing test run. Specify templ..." → src/pages/docs/api/run-tests/addevalconfigs.mdx
- (181 chars) "Compare evaluation summaries side-by-side across multiple test executions. Accep..." → src/pages/docs/api/run-tests/compareevalsummaries.mdx
- (162 chars) "Create a new test run with scenarios, agent definition, eval configs, and option..." → src/pages/docs/api/run-tests/createruntest.mdx
- (168 chars) "Delete an evaluation configuration from a test run by run test and eval config U..." → src/pages/docs/api/run-tests/deleteevalconfig.mdx
- (170 chars) "Trigger a new execution of a test run. Select scenarios by inclusion or exclusio..." → src/pages/docs/api/run-tests/executeruntest.mdx
- (165 chars) "List paginated call executions for a test run. Filter by status or search string..." → src/pages/docs/api/run-tests/getcallexecutions.mdx
- (161 chars) "Retrieve aggregated evaluation summary for a test run. Optionally scope to a spe..." → src/pages/docs/api/run-tests/getevalsummary.mdx
- (164 chars) "Retrieve full details of a test run by UUID, including agent definition, prompt ..." → src/pages/docs/api/run-tests/getruntestdetails.mdx
- (162 chars) "List paginated test executions for a run test. Filter by status or search string..." → src/pages/docs/api/run-tests/gettestexecutions.mdx
- (165 chars) "List paginated test runs. Filter by name, source type, or prompt template. Retur..." → src/pages/docs/api/run-tests/listruntests.mdx
- (162 chars) "Rerun test executions within a run test. Choose eval_only to re-evaluate existin..." → src/pages/docs/api/run-tests/reruntestexecutions.mdx
- (168 chars) "Run new evaluation configs on completed test executions. Specify eval config UUI..." → src/pages/docs/api/run-tests/runnewevalsontestexecution.mdx
- (159 chars) "Update an evaluation configuration for a test run. Modify config, mapping, model..." → src/pages/docs/api/run-tests/updateevalconfig.mdx
- (161 chars) "Update the agent definition, agent version, simulator agent, scenarios, or tool ..." → src/pages/docs/api/run-tests/updatetestcomponents.mdx
- (159 chars) "Add up to 10 AI-generated columns to a scenario dataset. Specify name, data type..." → src/pages/docs/api/scenarios/addcolumns.mdx
- (166 chars) "Add a specified number of empty rows to a scenario's dataset by dataset UUID. Ac..." → src/pages/docs/api/scenarios/addemptyrowstodataset.mdx
- (171 chars) "Generate and add 10–100 AI-populated rows to a scenario dataset. Provide optiona..." → src/pages/docs/api/scenarios/addscenariorowswithai.mdx
- (167 chars) "Create a simulation scenario from a dataset, script, or conversation graph. Supp..." → src/pages/docs/api/scenarios/createscenario.mdx
- (168 chars) "List paginated scenarios with optional search and filtering by agent definition ..." → src/pages/docs/api/scenarios/listscenarios.mdx
- (173 chars) "Retrieve latency, cost, and conversation metrics for a simulation run. Query by ..." → src/pages/docs/api/simulation-analytics/metrics.mdx
- (175 chars) "Retrieve simulation run records with eval scores, scenario metadata, and per-cal..." → src/pages/docs/api/simulation-analytics/runs.mdx
- (165 chars) "Cancel an in-progress test execution by UUID. Execution must be in pending, runn..." → src/pages/docs/api/test-executions/cancelexecution.mdx
- (178 chars) "Retrieve the AI-generated eval explanation summary for a test execution. Include..." → src/pages/docs/api/test-executions/getevalexplanationsummary.mdx
- (167 chars) "Retrieve pass/fail rates and top-performing scenarios for a test execution. Retu..." → src/pages/docs/api/test-executions/getperformancesummary.mdx
- (168 chars) "Retrieve a test execution by UUID with paginated call executions. Supports searc..." → src/pages/docs/api/test-executions/gettestexecutiondetails.mdx
- (171 chars) "Rerun call executions within a test execution. Choose eval_only to re-evaluate e..." → src/pages/docs/api/test-executions/reruncalls.mdx
- (162 chars) "Reference for all x-agentcc-* headers in Agent Command Center — control caching,..." → src/pages/docs/command-center/api/headers.mdx
- (160 chars) "Complete API reference for Agent Command Center — OpenAI-compatible endpoints, x..." → src/pages/docs/command-center/concepts/api-reference.mdx
- (162 chars) "Learn how Agent Command Center configuration works — hierarchy from request head..." → src/pages/docs/command-center/concepts/configuration.mdx
- (161 chars) "How Agent Command Center feeds signals into Future AGI Observe, Evaluate, Protec..." → src/pages/docs/command-center/concepts/platform-integration.mdx
- (161 chars) "Deploy Agent Command Center on your own infrastructure via Docker or Go binary —..." → src/pages/docs/command-center/deployment/self-hosted.mdx
- (156 chars) "Set per-key, per-org, and global RPM limits. Enforce monthly spend budgets and p..." → src/pages/docs/command-center/features/rate-limiting.mdx
- (156 chars) "Submit fire-and-forget async evaluations, poll job IDs for results, and run 50+ ..." → src/pages/docs/cookbook/quickstart/async-batch-eval.mdx
- (156 chars) "Define LLM quality criteria in plain English, register reusable eval metrics in ..." → src/pages/docs/cookbook/quickstart/custom-eval-metrics.mdx
- (158 chars) "Score RAG retrieval and generation quality independently with five metrics in on..." → src/pages/docs/cookbook/quickstart/rag-evaluation.mdx
- (157 chars) "Evaluate LLM outputs for professional tone, harmful content, and demographic bia..." → src/pages/docs/cookbook/quickstart/tone-toxicity-bias-eval.mdx
- (161 chars) "Simulate tool-calling agent conversations, trace every tool invocation as child ..." → src/pages/docs/cookbook/quickstart/tool-calling-simulation.mdx
- (157 chars) "Auto-score every production LLM response, set alerts for quality regressions, an..." → src/pages/docs/cookbook/use-cases/production-quality-monitoring.mdx
- (159 chars) "Full .env reference for self-hosted Future AGI — secrets, database credentials, ..." → src/pages/docs/self-hosting/environment.mdx
- (163 chars) "Production readiness checklist — replace secrets, configure TLS, set up managed ..." → src/pages/docs/self-hosting/production.mdx
- (166 chars) "Debug self-hosted Future AGI — symptoms, causes, and fixes for startup failures,..." → src/pages/docs/self-hosting/troubleshooting.mdx

## 6. Duplicate titles — 2 groups

**"Google GenAI Integration with Future AGI for Gemini Tracing"** (2 files)
  - src/pages/docs/integrations/google-genai.mdx
  - src/pages/docs/integrations/traceai/google_genai.mdx

**"OpenAI Agents SDK Integration with Future AGI Tracing"** (2 files)
  - src/pages/docs/integrations/openai-agents.mdx
  - src/pages/docs/integrations/traceai/openai_agents.mdx

## 7. First body heading ≠ `## About` — 434 files

- `## Accessing API Keys` → src/pages/docs/admin-settings.mdx
- `## What you will do` → src/pages/docs/annotations/quickstart.mdx
- `## Installation` → src/pages/docs/annotations/sdk/annotation-queue-using-sdk.mdx
- `# JavaScript SDK` → src/pages/docs/annotations/sdk/javascript.mdx
- `# Python SDK` → src/pages/docs/annotations/sdk/python.mdx
- `(no heading)` → src/pages/docs/api/agent-definitions/createagentdefinition.mdx
- `(no heading)` → src/pages/docs/api/agent-definitions/deleteagentdefinitions.mdx
- `(no heading)` → src/pages/docs/api/agent-definitions/fetchassistantfromprovider.mdx
- `(no heading)` → src/pages/docs/api/agent-definitions/getagentdefinition.mdx
- `(no heading)` → src/pages/docs/api/agent-definitions/listagentdefinitions.mdx
- `(no heading)` → src/pages/docs/api/agent-versions/createagentversion.mdx
- `(no heading)` → src/pages/docs/api/agent-versions/getagentversion.mdx
- `(no heading)` → src/pages/docs/api/agent-versions/getversioncallexecutions.mdx
- `(no heading)` → src/pages/docs/api/agent-versions/getversionevalsummary.mdx
- `(no heading)` → src/pages/docs/api/agent-versions/listagentversions.mdx
- `(no heading)` → src/pages/docs/api/annotations/bulk/bulk-annotate-spans.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/add-items.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/assign-items.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/bulk-remove-items.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/complete-item.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/get-annotate-detail.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/get-item-annotations.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/get-next-item.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/list-items.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/release-item.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/skip-item.mdx
- `(no heading)` → src/pages/docs/api/annotations/items/submit-annotations.mdx
- `(no heading)` → src/pages/docs/api/annotations/labels/create-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/labels/delete-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/labels/get-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/labels/list-labels.mdx
- `(no heading)` → src/pages/docs/api/annotations/labels/restore-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/labels/update-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/add-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/create-queue.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/delete-queue.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/export-to-dataset.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/export.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/find-queues-for-source.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/get-agreement.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/get-analytics.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/get-or-create-default.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/get-progress.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/get-queue.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/list-queues.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/remove-label.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/update-queue.mdx
- `(no heading)` → src/pages/docs/api/annotations/queues/update-status.mdx
- `(no heading)` → src/pages/docs/api/annotations/scores/bulk-create-scores.mdx
- `(no heading)` → src/pages/docs/api/annotations/scores/create-score.mdx
- `(no heading)` → src/pages/docs/api/annotations/scores/delete-score.mdx
- `(no heading)` → src/pages/docs/api/annotations/scores/get-scores-for-source.mdx
- `(no heading)` → src/pages/docs/api/annotations/scores/list-scores.mdx
- `(no heading)` → src/pages/docs/api/call-executions/getcallexecutiondetails.mdx
- `(no heading)` → src/pages/docs/api/call-executions/getsessioncomparison.mdx
- `(no heading)` → src/pages/docs/api/custom-eval-configs/check-config-exists.mdx
- `(no heading)` → src/pages/docs/api/custom-eval-configs/create-custom-eval-config.mdx
- `(no heading)` → src/pages/docs/api/custom-eval-configs/delete-custom-eval-config.mdx
- `(no heading)` → src/pages/docs/api/custom-eval-configs/get-custom-eval-config.mdx
- `(no heading)` → src/pages/docs/api/custom-eval-configs/list-configs-filtered.mdx
- `(no heading)` → src/pages/docs/api/custom-eval-configs/update-custom-eval-config.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/add-dataset-eval.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/create-custom-eval-template.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/delete-dataset-eval.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/edit-and-run-eval.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/get-eval-structure.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/get-eval-template-names.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/list-dataset-evals.mdx
- `(no heading)` → src/pages/docs/api/dataset-evals/start-evals-process.mdx
- `(no heading)` → src/pages/docs/api/datasets/add-as-new.mdx
- `(no heading)` → src/pages/docs/api/datasets/add-empty-rows.mdx
- `(no heading)` → src/pages/docs/api/datasets/add-rows-from-existing.mdx
- `(no heading)` → src/pages/docs/api/datasets/add-rows-from-file.mdx
- `(no heading)` → src/pages/docs/api/datasets/add-rows-from-huggingface.mdx
- `(no heading)` → src/pages/docs/api/datasets/analytics/annotation-summary.mdx
- `(no heading)` → src/pages/docs/api/datasets/analytics/eval-stats.mdx
- `(no heading)` → src/pages/docs/api/datasets/analytics/explanation-summary.mdx
- `(no heading)` → src/pages/docs/api/datasets/analytics/run-prompt-stats.mdx
- `(no heading)` → src/pages/docs/api/datasets/clone-dataset.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/add-columns.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/add-multiple-static-columns.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/add-static-column.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/delete-column.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/get-column-config.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/get-column-details.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/update-column-name.mdx
- `(no heading)` → src/pages/docs/api/datasets/columns/update-column-type.mdx
- `(no heading)` → src/pages/docs/api/datasets/create-dataset-from-huggingface.mdx
- `(no heading)` → src/pages/docs/api/datasets/create-dataset.mdx
- `(no heading)` → src/pages/docs/api/datasets/create-empty-dataset.mdx
- `(no heading)` → src/pages/docs/api/datasets/delete-dataset.mdx
- `(no heading)` → src/pages/docs/api/datasets/delete-rows.mdx
- `(no heading)` → src/pages/docs/api/datasets/duplicate-dataset.mdx
- `(no heading)` → src/pages/docs/api/datasets/duplicate-rows.mdx
- `(no heading)` → src/pages/docs/api/datasets/list-datasets.mdx
- `(no heading)` → src/pages/docs/api/datasets/merge-dataset.mdx
- `(no heading)` → src/pages/docs/api/datasets/run-prompt/add-run-prompt-column.mdx
- `(no heading)` → src/pages/docs/api/datasets/run-prompt/edit-run-prompt-column.mdx
- `(no heading)` → src/pages/docs/api/datasets/run-prompt/get-column-values.mdx
- `(no heading)` → src/pages/docs/api/datasets/run-prompt/get-model-voices.mdx
... and 334 more

## 8. Feature pages missing Next Steps / CardGroup — 3 files

- src/pages/docs/agent-playground/features/build-workflow.mdx
- src/pages/docs/agent-playground/features/create-graph.mdx
- src/pages/docs/agent-playground/features/run-and-monitor.mdx
