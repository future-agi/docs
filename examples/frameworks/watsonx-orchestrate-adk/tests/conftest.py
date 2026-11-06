import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
sys.path[:0] = [str(EXAMPLE), str(EXAMPLE / "tools")]

# agent.py builds its tracer and model client at import time; give them harmless values
# (nothing listens on :1, and the tests replace the model and add an in-memory exporter).
os.environ.setdefault("WXO_OTLP_ENDPOINT", "http://127.0.0.1:1/v1/traces")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("OTEL_BSP_SCHEDULE_DELAY", "60000")
os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", "1")  # the exit-time flush to :1 gives up fast
