# TH-8267 Claude Managed Agents: decision record

Date: 2026-10-16. Status: tracing stays deferred. Ships an updated "not supported yet" page, no package,
no relay, no collector config.

## Decision
Keep the deferral approved in PRD r2 / decision D-F2, with the page rewritten to current facts:
`src/pages/docs/integrations/claude-managed-agents.mdx`.

## Why the premise changed but the answer did not
- No longer true: PRD r2 said there is no OpenTelemetry export and that the SDK is TypeScript only (from
  LangSmith's page, read 2026-10-03). Anthropic now documents API tracing ("telemetry destinations", spans
  pushed from Anthropic's servers, including session turns, model requests with tokens and the tools it runs)
  and SDK tracing (spans from the Claude SDK in the customer's process). Managed Agents is in the Python,
  TypeScript, Java, Go, C#, Ruby and PHP SDKs. Sources, read 2026-10-16:
  https://platform.claude.com/docs/en/manage-claude/opentelemetry/api,
  https://platform.claude.com/docs/en/manage-claude/opentelemetry/sdk,
  https://platform.claude.com/docs/en/api/opentelemetry/spans.
- Also no longer true: compression is not a blocker. Anthropic gzips the first request of a delivery and
  resends uncompressed on a 400 or 415; the Future AGI collector answers gzip with 400 and accepts the resend.
- Still blocking:
  1. `project_name`. Anthropic's API spans carry only `service.name=claude-platform`; a destination can set
     headers but not resource attributes; the collector requires a `project_name` resource attribute
     (fi-collector `pkg/auth/stamp.go`, no header alternative). Every as-is delivery is rejected with 400.
  2. Reachability. A destination must be a public HTTPS hostname on port 443. Not tested; no tunnel was
     opened and no Future AGI Cloud endpoint was tried.
  3. Mapping. `invoke_agent` turns land as `unknown`; `anthropic.session.id` does not create a Future AGI
     session; `gen_ai.input.messages` / `gen_ai.output.messages` stay raw attributes (Input/Output empty);
     cost showed $0.00 for `claude-opus-5-5` locally.
  4. Spend. A real session needs an Anthropic key with billing (Claude models only, not ZDR eligible).

## Spike evidence (local Future AGI, project th8103-rest-claude-managed-agents, 2026-10-16). All STANDIN.
| Run | Trace id | Outcome |
| --- | --- | --- |
| API payload as Anthropic sends it | 87e6e6bf87aac4fdd93d247e2211e4e3 | gzip 400, uncompressed 400 `have no project_name`, not stored |
| API payload + project_name, metadata only | 719d989a-7b5b-4647-1f08-305aecabd670 | 5 spans: turn `unknown`, 2 x model_request `llm` (1834/41, 1907/18 tokens), tool_use `tool` |
| API payload + project_name, content | 511f0374-a48a-6d94-dd49-b5c3aa882270 | marker only in `spans.attrs_string` (turn, tool) |
| API payload + project_name, failure | 80a601b5-1113-af7b-c77e-2ed4c03b33d1 | turn and model_request ERROR (`rate_limit_error`) |
| SDK 1.15.0 vs stub, default | 058d9325-89c5-3f2f-fb1e-493e7b4a1468 | 7 spans incl. `anthropic.custom_tool_use count_files` (tool); marker absent from all 52 tables |
| SDK 1.15.0 vs stub, content mode | 08679c5a-172f-bc36-b899-47eed78bd38f | marker only in the custom tool span's `attrs_string` |
| SDK 1.15.0 vs stub, failure | 028d787f-6784-46e1-bda6-b32ef35b3a7f | `anthropic.sessions.retrieve` ERROR, `error.type=not_found_error`, empty status message |

fi_verify: PASS (6 traces, 29 spans; ERROR spans only in the two deliberate failure runs). No API key, user
name, host name or home path in any stored column. `run_e2e.sh` was re-run from a fresh venv with the same
outcome.

## Reopen when
1. Future AGI can take the project without a resource attribute (header or per-key default), or Future AGI
   decides to document and support a collector in front of it that adds `project_name` (a relay; not built).
2. The mapping above is in place (turn -> agent, `anthropic.session.id` -> session, gen_ai messages -> Input/Output).
3. A spend cap and a public HTTPS endpoint are approved, and one real session confirms the payload shape.
