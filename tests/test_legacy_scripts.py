"""Keep historical executable checks in the single pytest suite."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "tests" / "legacy").glob("check_*.py"))
assert len(SCRIPTS) == 11, "기존 자체 점검 파일이 누락되었습니다."


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.stem)
def test_legacy_check(script):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
