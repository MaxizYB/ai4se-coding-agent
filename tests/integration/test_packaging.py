import importlib.metadata as md
import subprocess


def test_package_importable():
    # installed via `pip install -e .` in bootstrap
    assert md.version("harness")


def test_console_script_entrypoint_works():
    # M2: the old test ran `python -c "from harness.cli import main; ..."` which
    # passes even if the [project.scripts] `harness = harness.cli:main` entry
    # point is misconfigured (it never invokes the installed console script).
    # This test invokes the REAL installed entrypoint (`harness key status`) so
    # a broken script wiring fails here. After `pip install -e .` the `harness`
    # binary is on PATH; `key status` on an empty store prints "(no keys
    # stored)" and exits 0. stderr is surfaced on failure for diagnostics.
    r = subprocess.run(
        ["harness", "key", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, (
        f"`harness key status` exited {r.returncode}\nstdout:\n{r.stdout}\n"
        f"stderr:\n{r.stderr}"
    )
    assert "(no keys stored)" in r.stdout, (
        f"expected '(no keys stored)' in output; got stdout=\n{r.stdout}\n"
        f"stderr=\n{r.stderr}"
    )
