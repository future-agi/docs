"""Render the first published SDK's reference without importing the dev API surface.

The 0.7.0/0.2.0 release predates the docs emitter. Only this immutable release
uses the bridge; later SDK releases must carry their own generated reference.
The emitter is also pinned. Its contract/catalog inputs ALWAYS come from the
published checkout, never the emitter checkout. Run in CI/cloud, not locally:

  python -I scripts/bootstrap-sdk-reference.py --sdk .sdk --renderer .sdk-renderer
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

RELEASE = "e61149de72c9907abd0921371126e4d40eb3e04a"
RENDERER = "3269d584fc668f959d8c125cf9acb33d3c36d1fb"


def head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--renderer", required=True, type=Path)
    args = parser.parse_args()
    sdk, renderer = args.sdk.resolve(), args.renderer.resolve()
    if head(sdk) != RELEASE or head(renderer) != RENDERER:
        raise ValueError("bootstrap requires the pinned published SDK and reviewed emitter commits")
    for root in (sdk, renderer):
        # Generated output may already exist for a deterministic rerun, but input
        # files must not be edited after checking out the verified commits.
        changed = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", "sdkgen", "python/fi/platform", "typescript/futureagi/src/platform"],
            text=True,
        )
        if changed.strip():
            raise ValueError("bootstrap inputs differ from their pinned commits")
    sys.path.insert(0, str(renderer))
    import yaml
    from sdkgen.generator import docs, python, typescript
    from sdkgen.generator.catalog import load

    spec = json.loads((sdk / "sdkgen/contracts/swagger.json").read_text())
    catalog = yaml.safe_load((sdk / "sdkgen/catalog/operations.yaml").read_text())
    ops = load(spec, catalog)
    # The emitter must see precisely the released operation definitions in both
    # languages, including parameters; merely counting method names is not enough.
    expected = {
        "python/fi/platform/_operations.py": python.emit_operations(ops),
        "typescript/futureagi/src/platform/_operations.ts": typescript.emit_operations(ops),
    }
    for name, text in expected.items():
        if (sdk / name).read_text() != text:
            raise ValueError(f"renderer inputs do not reproduce the released {name}")
    out = sdk / "docs/sdk-reference"
    out.mkdir(parents=True, exist_ok=True)
    for name, text in docs.emit_pages(spec, ops).items():
        (out / name).write_text(text)
    print(f"Rendered published SDK {RELEASE} using emitter {RENDERER}; {len(ops)} operations")


if __name__ == "__main__":
    main()
