# TH-8265 DeepSeek Harness: decision record

Date: 2026-10-16. Status: tracing stays deferred. Ships a "not supported yet" page, no package, no recipe.

## Decision
Keep the deferral approved in PRD r2 / decision D-F2. Publish `src/pages/docs/integrations/deepseek-harness.mdx` saying so.

## Why the premise changed but the answer did not
- At the historical pins: `deepseek-ai/deepseek-harness` has no trace export (`check_pin.sh`, three commits, positive controls pass). It only exports OTLP logs to a DeepSeek collector.
- No longer true: PRD r2 said no third-party OTel path exists. `@loongsuite/dsh-plugin` (Apache-2.0, created 2026-08-15) exports OTLP/HTTP traces and can be pointed at Future AGI. Spike below.
- Spike result: it works, but with content capture off it still exports the working directory, host name and raw provider error text, shows a failing shell command as OK, and fails silently on a bad key. Those concrete privacy and error-reporting issues are why this page supplies no customer setup. This is not a policy claim about every Future AGI integration.

## Spike evidence (local Future AGI, project th8103-rest-deepseek-harness, 2026-10-16)
| Run | dsh | Trace id | Outcome |
| --- | --- | --- | --- |
| content off | 0.2.1-alpha.4 | 280f18ea-bb5a-4602-5309-01838b7d95e8 | 7 spans, tree ok, tokens ok, marker absent |
| content on | 0.2.1-alpha.4 | 9c547d38-1ab2-5e7a-73ea-e189b3ce18ba | marker present in `spans.attrs_string` |
| content off | 0.2.0-rc.2 | 36900109-a56c-b2fc-de13-031c46fe065b | same shape, marker absent |
| failure (unknown model) | 0.2.1-alpha.4 | 7c738a79-61b1-2366-94fd-ab9fb421e701 | 4 spans, ERROR; raw 400 body in status message |
| tool exits 3 | 0.2.1-alpha.4 | 29f1033a-f428-636f-e42b-1c5b4ab714d9 | tool span OK |
| fresh run of run_e2e.sh, content off | 0.2.1-alpha.4 | f3fda9bb-14a7-9241-999e-00ed037ceb04 | 7 spans, marker absent from every stored column, host name present in resource attrs |

fi_verify: PASS (6 traces, 39 spans; the only ERROR spans are the 4 of the deliberate unknown-model run).
The model was an OpenAI-compatible local proxy standing in for the provider; no DeepSeek-hosted model was called.

## Reopen when
`dsh` or a reviewable plugin exports traces with no cwd, host name or raw error text by default, and marks failed tools as errors. Then decide on documenting the third-party plugin (needs a Future AGI product decision) and run `check_pin.sh` against the new head.

Source-only recheck, 2026-10-29: npm latest 0.2.1-rc.2 at 687f282e8625c6b8d11ff58211a90524be2e4317 has zero trace-term matches in packages/ and apps/; sdk-logs, JsonLogsSerializer and the logs collector URL all match. Plugin 0.1.3 remains current and its published code includes dsh.session.cwd and host.name. These checks do not extend the historical live-run scope.
