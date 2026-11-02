"""Exercise acceptance failures with synthetic docker, curl, and verifier stubs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
SCRATCH = HERE.parents[2]  # inside this isolated working copy


class AcceptanceExit(unittest.TestCase):
    def check_failure(self, fail_delivery, fail_verify):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as td:
            d = Path(td)
            bin_dir = d / "bin"
            bin_dir.mkdir()
            (bin_dir / "docker").write_text('#!/bin/sh\n[ "$1" = inspect ] && exit 1\nexit 0\n')
            (bin_dir / "curl").write_text('#!/bin/sh\nexit 0\n')
            (bin_dir / "sleep").write_text('#!/bin/sh\nexit 0\n')
            py = bin_dir / "fakepython"
            py.write_text('''#!/bin/sh
if [ "$1" = -I ] && [ "$2" = -c ]; then exec ''' + sys.executable + ''' "$@"; fi
if [ "$1" = -I ] && [ "${2##*/}" = run_collector_spike.py ]; then
  case "$4" in badtoken) ok=false;; *) ok=true;; esac
  if [ "$FAIL_DELIVERY" = 1 ] && [ "$4" = metadata ]; then ok=false; fi
  printf '{"deliveries":[{"delivered":%s}]}\\n' "$ok" > "$5"
  exit 0
fi
if [ "$1" = -I ]; then exec ''' + sys.executable + ''' "$@"; fi
printf 'PASS synthetic\\n'
[ "$FAIL_VERIFY" != 1 ]
''')
            for f in bin_dir.iterdir():
                f.chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                       FI_API_KEY="synthetic", FI_SECRET_KEY="synthetic", FI_BASE_URL="http://localhost:4318",
                       VERIFY=str(d / "verify.py"), PYTHON=str(py), OUT=str(d / "out"),
                       FAIL_DELIVERY=str(int(fail_delivery)), FAIL_VERIFY=str(int(fail_verify)))
            result = subprocess.run(["bash", str(HERE / "run_collector_e2e.sh")], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual((d / "out/failed.txt").read_text().strip(), "1")

    def test_delivery_failure_is_fatal(self):
        self.check_failure(True, False)

    def test_verification_failure_is_fatal_even_if_it_prints_pass(self):
        self.check_failure(False, True)


if __name__ == "__main__":
    unittest.main()
