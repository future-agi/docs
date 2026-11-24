"""Install the guide's command in the active test environment, without a shell."""

import re
import shlex
import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    page = (
        Path(__file__).resolve().parents[3]
        / "src/pages/docs/integrations/traceai/togetherai.mdx"
    )
    (command,) = re.findall(r"```bash\n(.*?)```", page.read_text(), re.DOTALL)
    args = shlex.split(command)
    if args[:3] != ["pip", "install", "--upgrade"]:
        raise ValueError("Expected the guide's pip install --upgrade command")
    subprocess.run([sys.executable, "-I", "-m", "pip", *args[1:]], check=True)
