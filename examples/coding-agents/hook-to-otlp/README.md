# hook-to-otlp

A small, stdlib-only Python (3.9+) hook command that turns a coding agent's
hook events into OTLP/HTTP spans for Future AGI. One agent session becomes one
trace. Docs page: <https://docs.futureagi.com/docs/integrations/coding-agents/hook-to-otlp>.

```
emit.py            CLI + core: state, span ids, parenting, privacy, export
adapters/base.py   the adapter contract (SpanEvent, scopes, phases, helpers)
adapters/<app>.py  one module per app (cursor.py, ...)
replay.py          feed a JSONL of recorded hook payloads through emit.py
tests/             unit + CLI tests; fixtures/<app>/*.jsonl
```

## Run

```bash
export FI_API_KEY=... FI_SECRET_KEY=...        # required, or nothing is sent
export FI_PROJECT_NAME=my-coding-agents        # default: the adapter name
# export FI_BASE_URL=https://api.futureagi.com # default; spans go to $FI_BASE_URL/tracer/v1/traces
echo '{"conversation_id":"c1","generation_id":"g1","tool_name":"Shell","duration":12}' \
  | python3 emit.py cursor postToolUse
```

`python3 emit.py <app> [<event>] [--env-file PATH]` reads one JSON object on
stdin, prints what the host expects on stdout (`{}` unless the adapter says
otherwise; nothing if the adapter cannot be loaded or the script fails), and exits 0. On macOS and Linux the network send happens in a
detached child process so the host is not kept waiting. Windows has no fork: the
send is inline (default timeout 3 s) and state files are not locked.

### Registering the hook (canonical guarded form)

Every app ships its hook commands in this form, so a missing emitter, a missing
`python3`, or a crash can never return exit code 2 (which many hosts treat as
"block") and never prints a decision:

```bash
(python3 -B <path-to>/emit.py <app> <EventName> 2>/dev/null || true)
```

`|| true` makes every failure exit 0 with empty stdout. The parentheses make it a
subshell, so the payload reaches `python3` whether the host pipes it to stdin or
appends it as a trailing heredoc (Cursor's headless agent host runs
`<command> <<'CURSOR_HOOK_EOF'`); without them the heredoc binds to `true` and the
emitter reads nothing. `2>/dev/null` keeps Python's own error text out of host logs
(the emitter never writes to stderr); `-B` keeps `__pycache__` out of the customer's
repo. Pass the event name explicitly. Do not add `echo` fallbacks (a second JSON object
is invalid output). The form needs a POSIX shell; document the equivalent on hosts whose
hook runner is not one (and note that a host that execs the command without a shell gets
no guard). Add a config test like `tests/test_cursor_hooks_config.py`: run every shipped
command through `sh -c` with the payload on stdin and as a trailing heredoc, with the
emitter missing, with `python3` missing, and installed, and assert exit 0 plus the
expected (or empty) stdout and that the installed emitter received the payload.

| Variable | Default | Meaning |
| --- | --- | --- |
| `FI_API_KEY`, `FI_SECRET_KEY` | none | Sent as `X-Api-Key` / `X-Secret-Key`. Missing: the hook is a no-op. |
| `FI_PROJECT_NAME` | adapter name | `project_name` resource attribute. |
| `FI_BASE_URL` | `https://api.futureagi.com` | Spans go to `$FI_BASE_URL/tracer/v1/traces`. |
| `FI_OTLP_ENDPOINT` | none | Full traces URL; overrides `FI_BASE_URL`. |
| `FI_HOOK_CAPTURE_CONTENT` | off | `1` exports prompts, tool input/output, model text, error text. |
| `FI_HOOK_MAX_CONTENT_CHARS` | `4096` | Per-field cap when content is on. |
| `FI_HOOK_TIMEOUT` | `10` (`3` without `fork`, i.e. Windows) | HTTP timeout in seconds. On macOS/Linux the send runs in a detached process, so the host never waits on it; on Windows it is inline. |
| `FI_HOOK_SYNC` | off | `1` sends inline instead of in a detached child (tests, debugging). |
| `FI_HOOK_STATE_DIR` | `$TMPDIR/fi-hook-to-otlp-<uid>` | Per-session state files (0600, removed at session end, swept after 24 h). With content on they also hold the content of spans that have not ended yet (for example the open turn's prompt) and of up to 8 turns closed as incomplete; completed turns keep no content. |
| `FI_HOOK_LOG_FILE` | none | One line per hook: event, span count, HTTP status. No content, no keys. |
| `FI_HOOK_DUMP_FILE` | none | Appends each OTLP/JSON body exactly as sent (privacy checks). |
| `FI_HOOK_DISABLED` | off | `1` turns the hook into a no-op. |
| `FI_HOOK_ENV_FILE` | `~/.config/fi-hook-to-otlp/env` | `KEY=VALUE` file read for `FI_*` keys missing from the environment (GUI apps often start without your shell env). |

## Span model

| Scope | Parent | Default `fi.span.kind` | Exported when |
| --- | --- | --- | --- |
| session | none (root) | `AGENT` | with every batch that exports a child span, and at session end (same span id and start time each time, so the latest export wins). A session with no activity is never exported. |
| turn | session | `CHAIN` | turn end |
| tool | turn, else session | `TOOL` | tool end |
| subagent | turn, else session | `AGENT` | subagent end |
| llm | turn, else session | `LLM` | instantly |
| event | turn, else session | `CHAIN` | instantly |

- Trace id = `sha256("trace", app, session_id)[:32]`; span ids are derived from
  `(app, session_id, scope, key)`, so retries of the same hook overwrite rather than duplicate.
- A span's start is the matching START hook if one was seen, else `end - duration_ms`
  from the payload, else the hook time, never earlier than the root's start once the
  root has been sent. A turn opens on the first event that names it.
- A tool/subagent/llm/event span without `turn_id` goes under the open turn and gets
  `coding_agent.turn.inferred=true`; with no open turn it goes under the session with no
  turn marker.
- A turn end closes still-open children of that turn (`coding_agent.incomplete=true`);
  a session end closes everything and deletes the state file.
- One turn is open per session: a turn START closes any other open turn (and its
  children) as incomplete. If that turn's END arrives later, the turn is re-sent complete
  with its original start.
- Every span carries `session.id`, `gen_ai.conversation.id`, `coding_agent.app`,
  `coding_agent.scope`, `coding_agent.hook.event`, and `coding_agent.turn.id` when known.
  Tool spans add `gen_ai.tool.name` and `gen_ai.tool.call.id`; session/turn/llm/subagent
  spans add `llm.model_name` when the payload names a model (the root uses the last model
  reported by a session, turn or llm event).
- Opted-in content keeps paths but replaces the user name in home-directory paths with
  `<user>` (`/Users/<user>/...`, `/home/<user>/...`, `C:\Users\<user>\...`, `~<user>/...`),
  including names with spaces when a path separator follows them, and this machine's own
  home directory wherever it appears.

## Writing an adapter

Create `adapters/<app>.py` (module name = app slug, `[a-z0-9_]+`):

```python
from adapters.base import END, START, SESSION, TOOL, TURN, OK, ERROR, SpanEvent, compact, first, number

APP = "myapp"
DISPLAY_NAME = "My App"          # "My App session", "My App turn"
SERVICE_NAME = "myapp"           # optional, resource service.name

def parse(event: str, payload: dict) -> list:           # required
    sid = first(payload, "session_id")
    if not sid:
        return []                                       # never invent a session id
    if event == "PostToolUse":
        return [SpanEvent(END, TOOL, str(sid), key=payload.get("tool_use_id", ""),
                          name=payload.get("tool_name"), duration_ms=number(payload.get("duration_ms")),
                          input=payload.get("tool_input"), output=payload.get("tool_response"))]
    return []

def respond(event: str, payload: dict) -> str:          # optional, default "{}"
    return "{}"                                         # "" prints nothing (hosts that add stdout to the model context)

def event_name(argv_event, payload):                    # optional
    return argv_event or payload.get("hook_event_name")

def resource_attributes(event: str, payload: dict) -> dict:   # optional, metadata only
    return compact({"coding_agent.app.version": payload.get("version")})
```

`SpanEvent(phase, scope, session_id, key="", turn_id=None, name=None, kind=None,
attributes={}, model=None, duration_ms=None, status=None, status_message=None,
input=None, output=None, error_message=None)`:

- `phase`: `START` opens, `END` closes and exports, `INSTANT` exports a complete span,
  `UPDATE` merges into an open span (for example a response text into the turn).
- `scope`: `SESSION`, `TURN`, `TOOL`, `SUBAGENT`, `LLM`, `EVENT`.
- `key` pairs START/END of the same scope (tool call id, turn id). Empty for the session.
  Apps without ids can leave it empty: a keyless TURN START opens `turn-1`, `turn-2`, ...
  and a keyless TURN END/UPDATE applies to the open turn (ignored if none); a keyless
  END of another scope pairs with the oldest open keyless START of the same scope and
  `name` (FIFO), else it becomes a standalone span.
- `turn_id` parents a tool/subagent/llm/event span; None means the open turn, else the session.
- `status` is `OK`, `ERROR` or None. `status_message` is always exported, so keep it to
  metadata (`"timeout"`), never free text.
- `input`, `output`, `error_message` are content: dropped unless `FI_HOOK_CAPTURE_CONTENT=1`.
- `attributes` are always exported: ids, names, counts, enums only. Namespace them
  `<app>.*`. Never emails, file paths, transcript paths, or text bodies.

Do not wire the emitter to hooks whose output decides whether the agent may act
(permission hooks): the emitter observes, it does not approve. If an app requires an
answer on such a hook, `respond()` must not approve; return `""` (print nothing) when
the app treats no output as "no decision", as the Cursor adapter does.

Add `tests/fixtures/<app>/session.jsonl` (`{"event": ..., "payload": ...}` per line,
shaped exactly like the vendor docs) and `tests/test_<app>_adapter.py`. The Cursor
adapter and its test are the reference.

## Test

```bash
python3 -m unittest discover -s tests -t .
# replay a recorded session into a real collector with a fresh session id
python3 replay.py cursor tests/fixtures/cursor/session.jsonl --replace fixture-conv-0001=run-$(date +%s)
# same, through the commands of an installed hooks file, payload as a trailing heredoc
python3 replay.py cursor tests/fixtures/cursor/session.jsonl --replace fixture-conv-0001=run-$(date +%s) \
  --hooks-json /path/to/project/.cursor/hooks.json --cwd /path/to/project --transport heredoc
```
