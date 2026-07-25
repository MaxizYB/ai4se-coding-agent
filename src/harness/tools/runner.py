import os
import subprocess
from dataclasses import dataclass


@dataclass
class TestRunOutput:
    __test__ = False  # silence pytest collection warning (F9)
    exit_code: int
    stdout: str
    stderr: str
    junit_xml: str


def run_tests(command: list[str], cwd: str, timeout: int, junit_path: str) -> TestRunOutput:
    # The agent edits source between runs; a `.pyc` written by an earlier run
    # can be reused on a fast re-run when the filesystem mtime is coarse (e.g.
    # /tmp tmpfs within the same second), so the loop sees stale code and can
    # never observe green. Suppress bytecode emission so source stays authoritative.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        p = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        xml = ""
        try:
            with open(junit_path) as f:
                xml = f.read()
        except FileNotFoundError:
            xml = ""
        return TestRunOutput(p.returncode, p.stdout, p.stderr, xml)
    except subprocess.TimeoutExpired as e:
        return TestRunOutput(124, e.stdout or "", f"subprocess.TimeoutExpired: {timeout}s", "")
