import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "native", "tools"):
    path = os.path.join(ROOT, sub) if sub else ROOT
    if path not in sys.path:
        sys.path.insert(0, path)
