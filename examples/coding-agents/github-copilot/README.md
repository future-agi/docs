# GitHub Copilot -> Future AGI

GitHub Copilot CLI and VS Code Copilot Chat export OpenTelemetry traces natively.
Nothing here runs inside Copilot: these files configure Copilot's own exporter
and check what it sends. Docs page:
<https://docs.futureagi.com/docs/integrations/coding-agents/github-copilot>.

| File | Purpose |
| --- | --- |
| `copilot-otel.env.example` | `OTEL_*` variables for the CLI (and for the shell you start VS Code from) |
| `vscode-settings.json` | `github.copilot.chat.otel.*` user settings for VS Code |
| `run_e2e.sh` | one real Copilot CLI session in a throwaway folder, exported to Future AGI |
| `check_spans.py` | checks a Copilot span dump (file exporter JSON lines) against the recipe contract |
| `fixtures/copilot-cli-1.0.98-default.jsonl` | sanitized spans from a real Copilot CLI 1.0.98 session, content capture off |

```bash
export FI_API_KEY=... FI_SECRET_KEY=...
./run_e2e.sh                       # content off (default)
CAPTURE_CONTENT=1 ./run_e2e.sh     # opt in to prompt/tool content for one run
python3 -m unittest test_check_spans
```

`check_spans.py` accepts both the CLI file-exporter records and direct span objects written by the VS Code file exporter. It ignores standalone `custom_notification` records when checking the agent tree.
