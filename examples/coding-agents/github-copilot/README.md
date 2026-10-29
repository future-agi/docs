# GitHub Copilot -> Future AGI

This customer recipe covers GitHub Copilot CLI 1.0.98 native OpenTelemetry export only. VS Code Copilot Chat is outside its qualification.
Nothing here runs inside Copilot: these files configure Copilot's own exporter
and check what it sends. Docs page:
<https://docs.futureagi.com/docs/integrations/coding-agents/github-copilot>.

| File | Purpose |
| --- | --- |
| `copilot-otel.sh` | `copilot` shell function that sets the `OTEL_*` exporter variables on the Copilot process only and hides the keys from Copilot's shell commands and MCP servers (`--secret-env-vars`) |
| `vscode-settings.json` | Development reference only; not a qualified Future AGI VS Code setup |
| `run_e2e.sh` | one real Copilot CLI session in a throwaway folder, exported to Future AGI |
| `check_spans.py` | checks a Copilot span dump (file exporter JSON lines) against the recipe contract |
| `fixtures/copilot-cli-1.0.98-default.jsonl` | sanitized spans from a real Copilot CLI 1.0.98 session, content capture off |

```bash
FI_API_KEY=... FI_SECRET_KEY=... ./run_e2e.sh                     # content off (default)
FI_API_KEY=... FI_SECRET_KEY=... CAPTURE_CONTENT=1 ./run_e2e.sh   # opt in to prompt/tool content for one run
python3 -m unittest test_check_spans
```

`run_e2e.sh` uses the same scoping as the wrapper: the exporter variables are set on the `copilot` command only, and `--secret-env-vars` keeps the keys out of the shell commands Copilot runs.

`check_spans.py` accepts both the CLI file-exporter records and direct span objects written by the VS Code file exporter. It ignores standalone `custom_notification` records when checking the agent tree.
