import importlib.metadata as md
import subprocess
import sys


def test_package_importable():
    # installed via `pip install -e .` in bootstrap
    assert md.version("harness")


def test_console_script_exists():
    r = subprocess.run(
        [sys.executable, "-c", "from harness.cli import main; print(callable(main))"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "True" in r.stdout
