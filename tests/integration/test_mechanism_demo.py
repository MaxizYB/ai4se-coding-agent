import subprocess
import sys


def test_demo_runs_offline_and_exits_zero():
    r = subprocess.run(
        [sys.executable, "scripts/mechanism_demo.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "①" in r.stdout and "②" in r.stdout and "③" in r.stdout
