"""Run installed application checks with an isolated personal-data directory."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    with tempfile.TemporaryDirectory(prefix="strident-verification-") as folder:
        env = {**os.environ, "LOCALAPPDATA": folder, "QT_QPA_PLATFORM": "offscreen",
               "PYTHONUTF8": "1"}
        print("Verifying with isolated test data; your personal database is not used.", flush=True)
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                                cwd=Path(__file__).resolve().parent, env=env, check=False)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
