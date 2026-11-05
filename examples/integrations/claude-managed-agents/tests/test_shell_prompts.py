"""The published credential prompts must work in both common reader shells."""
import pathlib
import re
import subprocess
import unittest

PAGE = (pathlib.Path(__file__).resolve().parents[4] / "src/pages/docs/integrations/claude-managed-agents.mdx").read_text()


class PublishedShellPrompts(unittest.TestCase):
    def test_setup_prompts_in_bash_and_zsh(self):
        # Exercise exactly the read/print lines shown in the setup blocks, with
        # synthetic values and no collector, API call, or credential access.
        names = ("FI_API_KEY", "FI_SECRET_KEY", "ANTHROPIC_ADMIN_API_KEY", "ANTHROPIC_WORKSPACE_ID")
        prompt_lines = []
        for name in names:
            lines = [line for line in PAGE.splitlines() if re.search(r"\bread\b.*\b" + name + r"\b", line)]
            self.assertEqual(len(lines), 1, name)
            prompt_lines.extend(lines)
        script = "set -e\n" + "\n".join(prompt_lines) + "\n" + "\n".join(
            f'test "${{{name}}}" = "synthetic_{name}"' for name in names
        ) + "\n"
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell):
                result = subprocess.run(
                    [shell, "-c", script],
                    input="".join(f"synthetic_{name}\n" for name in names),
                    text=True, capture_output=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
