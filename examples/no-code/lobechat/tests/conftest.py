import pathlib
import sys

EXAMPLE = pathlib.Path(__file__).resolve().parents[1]
REPO = EXAMPLE.parents[2]
sys.path.insert(0, str(EXAMPLE / "tools"))
sys.path.insert(0, str(EXAMPLE / "mcp"))
