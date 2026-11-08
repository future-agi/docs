"""CI-only check of published plugin discovery; no model or Future AGI calls.

Run in a fresh Hermes home after installation, then again with --enabled after
`hermes plugins enable futureagi`. INSTALL_ROUTE selects pip or directory.
"""

import argparse
import os
from importlib.metadata import entry_points, version
from pathlib import Path

from hermes_cli.plugins import VALID_HOOKS, PluginManager
from traceai_hermes_agent._recorder import HOOKS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enabled", action="store_true")
    args = parser.parse_args()
    route = os.environ["INSTALL_ROUTE"]
    assert route in {"pip", "directory"}, route
    assert version("hermes-agent") == "0.21.5"
    assert version("traceAI-hermes-agent") == "0.1.1"
    assert set(HOOKS) <= VALID_HOOKS
    assert "pre_tool_call" not in HOOKS
    assert any(
        ep.name == "futureagi" and ep.value == "traceai_hermes_agent:register"
        for ep in entry_points(group="hermes_agent.plugins")
    )

    directory = Path(os.environ["HERMES_HOME"]) / "plugins" / "futureagi"
    assert directory.exists() == (route == "directory")
    manager = PluginManager()
    manager.discover_and_load()
    plugins = [item for item in manager.list_plugins() if item["name"] == "futureagi"]
    assert len(plugins) == 1, plugins  # Directory and entry point must not double-load.
    plugin = plugins[0]
    assert plugin["source"] == ("entrypoint" if route == "pip" else "user"), plugin
    assert plugin["enabled"] == args.enabled, plugin
    if args.enabled:
        assert not plugin["error"], plugin
    else:
        assert plugin["error"] == (
            "not enabled in config (run `hermes plugins enable futureagi` to activate)"
        ), plugin
    assert plugin["hooks"] == (len(tuple(HOOKS)) if args.enabled else 0), plugin
    print(f"Released {route} plugin: enabled={args.enabled}, hooks={plugin['hooks']}")


if __name__ == "__main__":
    main()
