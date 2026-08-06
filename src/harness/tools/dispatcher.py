import os
import subprocess
from dataclasses import dataclass

from harness.actions.protocol import (
    Action,
    EditFile,
    GrepSearch,
    ListDir,
    ReadFile,
    RunShell,
    RunTests,
    WriteFile,
)
from harness.config import Config
from harness.tools.runner import run_tests


@dataclass
class ToolResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    junit_xml: str = ""


class ToolDispatcher:
    def __init__(self, config: Config, test_runner=None):
        self.config = config
        self.test_runner = test_runner or run_tests

    def _abs(self, path: str) -> str:
        return os.path.join(self.config.project_root, path)

    def execute(self, action: Action) -> ToolResult:
        if isinstance(action, ReadFile):
            try:
                with open(self._abs(action.path)) as f:
                    return ToolResult(True, f.read(), "", 0)
            except OSError as e:
                return ToolResult(False, "", str(e), 1)
        if isinstance(action, ListDir):
            try:
                return ToolResult(True, "\n".join(os.listdir(self._abs(action.path))), "", 0)
            except OSError as e:
                return ToolResult(False, "", str(e), 1)
        if isinstance(action, WriteFile):
            os.makedirs(os.path.dirname(self._abs(action.path)) or ".", exist_ok=True)
            with open(self._abs(action.path), "w") as f:
                f.write(action.content)
            return ToolResult(True, f"wrote {action.path}", "", 0)
        if isinstance(action, EditFile):
            p = self._abs(action.path)
            with open(p) as f:
                text = f.read()
            if action.old not in text:
                return ToolResult(False, "", "old block not found", 1)
            with open(p, "w") as f:
                f.write(text.replace(action.old, action.new, 1))
            return ToolResult(True, f"edited {action.path}", "", 0)
        if isinstance(action, GrepSearch):
            from harness.memory.retriever import Retriever
            root = os.path.join(self.config.project_root, action.path)
            hits = Retriever.grep(action.pattern, root if os.path.isdir(root) else self.config.project_root)
            return ToolResult(True, "\n".join(hits) if hits else "(no matches)", "", 0)
        if isinstance(action, RunShell):
            # agent can drive interactive CLIs (e.g. feed moves to a game).
            # Empty string = immediate EOF (no hang on a TTY) — safer than the
            # old behavior of inheriting the parent's stdin.
            r = subprocess.run(
                action.command,
                cwd=self.config.project_root,
                shell=True,
                input=action.stdin,
                capture_output=True,
                text=True,
                check=False,
            )
            return ToolResult(r.returncode == 0, r.stdout, r.stderr, r.returncode)
        if isinstance(action, RunTests):
            # Fix E: ABSOLUTE junit path. With a relative `project_root` (e.g.
            # `examples/demo`), a relative junit path is resolved differently
            # by pytest (relative to its cwd=project_root) vs the reader
            # (relative to the harness process cwd) -> the junit file is never
            # found -> FeedbackEngine falls back to stderr and misreads GREEN
            # runs as UNKNOWN. Absolute path makes both agree. Mock tests used
            # absolute `tmp_path` so never caught this.
            junit = os.path.abspath(os.path.join(self.config.project_root, ".harness", "junit.xml"))
            os.makedirs(os.path.dirname(junit), exist_ok=True)
            args = action.args.split() if action.args else []
            out = self.test_runner(
                ["pytest", "--junitxml", junit, "--tb=short", *args],
                self.config.project_root,
                self.config.test_timeout_s,
                junit,
            )
            return ToolResult(out.exit_code == 0, out.stdout, out.stderr, out.exit_code, out.junit_xml)
        return ToolResult(False, "", f"unknown action {type(action).__name__}", 1)
