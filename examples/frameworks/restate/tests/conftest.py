import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path[:0] = [str(EXAMPLE), str(EXAMPLE / "tools")]

# agent_service.py builds its clients at import time; give it harmless values (nothing listens on :1).
os.environ.setdefault("FI_API_KEY", "test-api-key")
os.environ.setdefault("FI_SECRET_KEY", "test-secret-key")
os.environ.setdefault("FI_BASE_URL", "http://127.0.0.1:1")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
