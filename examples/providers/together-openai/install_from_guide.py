"""Run the guide's venv, activation and pinned install commands in the job workspace."""

import re
import subprocess
from pathlib import Path


if __name__ == "__main__":
    page = (
        Path(__file__).resolve().parents[3]
        / "src/pages/docs/integrations/traceai/togetherai.mdx"
    )
    (block,) = re.findall(r"```bash\n(.*?)```", page.read_text(), re.DOTALL)
    if block.splitlines() != [
        "python3 -m venv .venv",
        "source .venv/bin/activate",
        "python -m pip install traceAI-openai==0.1.16 fi-instrumentation-otel==1.5.1 "
        '"openai>=1,<2" httpx==0.28.1',
    ]:
        raise ValueError("Expected the published venv setup and pinned requirements")
    # Use the literal block, including its shell quoting and activation.
    subprocess.run(["bash", "-ec", block], check=True)
