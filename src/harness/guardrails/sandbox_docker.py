import os
import subprocess

from harness.actions.protocol import RunShell, RunTests
from harness.config import Config
from harness.tools.dispatcher import ToolResult


class SandboxDockerExecutor:
    """Hard-isolation executor: runs shell/tests inside a throwaway container.

    G5 — the ``Containerize`` path. When ``config.sandbox_containerize`` is set,
    the Sandbox gate flags surviving ``RunShell``/``RunTests`` actions as
    ``Containerize`` and the loop routes them here instead of the host
    dispatcher. Each call builds a one-shot container with:

      * ``--network=none``  — fully offline (no egress, no exfiltration);
      * ``--read-only``     — the container's root filesystem is immutable;
      * ``--tmpfs /tmp``    — a scratch tmpfs so /tmp stays writable;
      * ``-v <repo>:/work`` — the repo bind-mounted read-write at /work;
      * ``-w /work``        — /work is the working directory.

    The container is removed on exit (``--rm``). ``runner`` is injectable so the
    argv can be asserted in mock tests without a real Docker daemon.
    """

    def __init__(self, config: Config, runner=None):
        self.config = config
        # Default to the real subprocess.run; tests inject a recording fake.
        self.runner = runner or subprocess.run

    def _base_argv(self) -> list[str]:
        repo = os.path.abspath(self.config.project_root)
        return [
            "docker", "run", "--rm",
            "--network=none",
            "--read-only",
            "--tmpfs", "/tmp",
            "-v", f"{repo}:/work",
            "-w", "/work",
            self.config.sandbox_container_image,
        ]

    def run_shell(self, action: RunShell) -> ToolResult:
        argv = self._base_argv() + ["sh", "-c", action.command]
        r = self.runner(argv, input=action.stdin, capture_output=True, text=True, check=False)
        return ToolResult(r.returncode == 0, r.stdout, r.stderr, r.returncode)

    def run_tests(self, action: RunTests) -> ToolResult:
        # /work is the bind-mounted repo, so the junit file written inside the
        # container lands on the host at <repo>/.harness/junit.xml and is read
        # back after the run -- mirrors the host dispatcher's junit contract.
        junit_in_container = "/work/.harness/junit.xml"
        args = action.args.split() if action.args else []
        argv = self._base_argv() + [
            "pytest", "--junitxml", junit_in_container, "--tb=short", *args,
        ]
        r = self.runner(argv, input="", capture_output=True, text=True, check=False)
        junit_xml = ""
        junit_host = os.path.join(
            os.path.abspath(self.config.project_root), ".harness", "junit.xml"
        )
        try:
            with open(junit_host) as f:
                junit_xml = f.read()
        except OSError:
            # Container may fail before pytest writes junit (e.g. image missing,
            # import error). Leave junit_xml blank; FeedbackEngine falls back to
            # stdout/stderr exactly like the host dispatcher.
            pass
        return ToolResult(r.returncode == 0, r.stdout, r.stderr, r.returncode, junit_xml)
