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
    # Marker-only would pass even if the internal asserts were deleted; lock the
    # mechanism-specific substrings each demo prints, so removing an internal
    # assertion (or a regression in the underlying mechanism) fails this test.
    assert "AskHuman" in r.stdout          # demo ① — guardrail intercept
    assert "修实现逻辑" in r.stdout          # demo ② — LOGIC strategy hint
    assert "TIMEOUT" in r.stdout           # demo ③ — category label
