import subprocess
from dataclasses import dataclass


@dataclass
class TestRunOutput:
    exit_code: int
    stdout: str
    stderr: str
    junit_xml: str


def run_tests(command: list[str], cwd: str, timeout: int, junit_path: str) -> TestRunOutput:
    try:
        p = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
        xml = ""
        try:
            with open(junit_path) as f:
                xml = f.read()
        except FileNotFoundError:
            xml = ""
        return TestRunOutput(p.returncode, p.stdout, p.stderr, xml)
    except subprocess.TimeoutExpired as e:
        return TestRunOutput(124, e.stdout or "", f"subprocess.TimeoutExpired: {timeout}s", "")
