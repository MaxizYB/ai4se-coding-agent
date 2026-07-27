import io
import os
import subprocess
from dataclasses import dataclass

import pytest

from harness.actions.protocol import RunShell, RunTests
from harness.config import Config
from harness.guardrails.sandbox_docker import SandboxDockerExecutor
from harness.tools.dispatcher import ToolResult


@dataclass
class FakeCompletedProcess:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class FakeRunner:
    """Records the argv + kwargs it was called with, returns a canned result."""

    def __init__(self, result=None):
        self.calls: list[tuple[list, dict]] = []
        self.result = result or FakeCompletedProcess(stdout="hi\n", stderr="", returncode=0)

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        return self.result


def cfg(tmp_path, **kw):
    c = Config.default()
    c.project_root = str(tmp_path)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# --- run_shell: hardened throwaway-container argv ----------------------------


def test_run_shell_builds_hardened_container_argv(tmp_path):
    c = cfg(tmp_path)
    fake = FakeRunner(FakeCompletedProcess(stdout="hi\n", stderr="warn", returncode=0))
    res = SandboxDockerExecutor(c, runner=fake).run_shell(RunShell("echo hi"))

    argv, _ = fake.calls[0]
    repo = os.path.abspath(str(tmp_path))
    # hardened isolation flags
    assert argv[:3] == ["docker", "run", "--rm"]
    assert "--network=none" in argv
    assert "--read-only" in argv
    assert "--tmpfs" in argv and "/tmp" in argv
    # repo bind-mounted at /work (read-write) and used as working dir
    assert "-v" in argv and f"{repo}:/work" in argv
    assert "-w" in argv and "/work" in argv
    # configured image, then the sh -c <command> entrypoint
    i = argv.index(c.sandbox_container_image)
    assert argv[i + 1 : i + 4] == ["sh", "-c", "echo hi"]
    # ToolResult carries the CompletedProcess fields
    assert isinstance(res, ToolResult)
    assert res.stdout == "hi\n" and res.stderr == "warn" and res.exit_code == 0 and res.ok is True


def test_run_shell_pipes_stdin(tmp_path):
    fake = FakeRunner()
    SandboxDockerExecutor(cfg(tmp_path), runner=fake).run_shell(RunShell("cat", stdin="hello"))
    _, kwargs = fake.calls[0]
    assert kwargs["input"] == "hello"


def test_run_shell_nonzero_exit_marked_not_ok(tmp_path):
    fake = FakeRunner(FakeCompletedProcess(stdout="", stderr="boom", returncode=2))
    res = SandboxDockerExecutor(cfg(tmp_path), runner=fake).run_shell(RunShell("false"))
    assert res.ok is False and res.exit_code == 2 and res.stderr == "boom"


def test_run_shell_uses_configured_image(tmp_path):
    c = cfg(tmp_path, sandbox_container_image="myimg:dev")
    fake = FakeRunner()
    SandboxDockerExecutor(c, runner=fake).run_shell(RunShell("ls"))
    assert "myimg:dev" in fake.calls[0][0]


# --- run_tests: pytest entrypoint + junit read-back --------------------------


def test_run_tests_builds_pytest_argv(tmp_path):
    c = cfg(tmp_path)
    fake = FakeRunner(FakeCompletedProcess(stdout="", stderr="ERR", returncode=1))
    res = SandboxDockerExecutor(c, runner=fake).run_tests(RunTests("tests/t.py::test_a"))

    argv = fake.calls[0][0]
    assert "pytest" in argv
    i = argv.index("--junitxml")
    assert argv[i + 1] == "/work/.harness/junit.xml"
    assert "--tb=short" in argv
    assert "tests/t.py::test_a" in argv
    # still inside the hardened container
    assert "--network=none" in argv and "--read-only" in argv
    assert res.exit_code == 1 and res.ok is False and res.stderr == "ERR"


def test_run_tests_reads_junit_xml_back_from_mount(tmp_path):
    c = cfg(tmp_path)
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "junit.xml").write_text("<xml>results</xml>")
    fake = FakeRunner()
    res = SandboxDockerExecutor(c, runner=fake).run_tests(RunTests())
    # /work is the bind-mounted repo, so the container's junit file lands on
    # the host at <repo>/.harness/junit.xml and is read into ToolResult.junit_xml.
    assert res.junit_xml == "<xml>results</xml>"


def test_run_tests_missing_junit_leaves_blank(tmp_path):
    fake = FakeRunner()
    res = SandboxDockerExecutor(cfg(tmp_path), runner=fake).run_tests(RunTests())
    assert res.junit_xml == ""


# --- default runner is the real subprocess.run --------------------------------


def test_default_runner_is_subprocess_run():
    ex = SandboxDockerExecutor(Config.default())
    assert ex.runner is subprocess.run


# --- loop wiring: Containerize branch routes to the docker executor -----------
# (mock-level; NO real docker. Proves G5 wiring in both runners.)


class RecordingDispatcher:
    """Host dispatcher stub: records any action that reaches execute()."""

    def __init__(self):
        self.calls = []

    def execute(self, action):
        self.calls.append(action)
        return ToolResult(True, "host-dispatch", "", 0)


def _build_chat(tmp_path, script, *, containerize):
    from harness.context.manager import ContextManager
    from harness.feedback.engine import FeedbackEngine
    from harness.guardrails.guardrail import Guardrail
    from harness.guardrails.hitl import HITL, FailClosedApprover
    from harness.guardrails.sandbox import Sandbox
    from harness.interactive.chat import ChatRunner
    from harness.interactive.presenter import Presenter
    from harness.llm.mock import MockLLMClient
    from harness.memory.store import MemoryStore

    (tmp_path / "src").mkdir()
    c = Config.default()
    c.project_root = str(tmp_path)
    c.sandbox_containerize = containerize
    c.diff_preview = "never"
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(c, mem)
    pres = Presenter(out=io.StringIO())
    host = RecordingDispatcher()
    docker = SandboxDockerExecutor(c, runner=FakeRunner(FakeCompletedProcess(stdout="container-out\n")))
    r = ChatRunner(
        MockLLMClient(script),
        c,
        host,
        Guardrail(c),
        HITL(FailClosedApprover()),
        FeedbackEngine(c.test_timeout_s, c.stuck_repeat_n, c.stuck_no_progress_m, c.hint_history_lines),
        cm,
        pres,
        sandbox=Sandbox(c),
        sandbox_docker=docker,
    )
    return r, host, docker


def test_chat_containerize_routes_run_shell_to_docker(tmp_path):
    script = [
        "run.\nACTION: run_shell\nCOMMAND: echo hi\n",
        "ACTION: finish\nREASON: done\n",
    ]
    r, host, docker = _build_chat(tmp_path, script, containerize=True)
    r.run_task(str(tmp_path), "run echo hi")
    assert docker.runner.calls, "containerized RunShell should hit the docker executor"
    assert not host.calls, "host dispatcher must not run a containerized action"


def test_chat_no_docker_falls_back_to_host_dispatcher(tmp_path):
    script = [
        "run.\nACTION: run_shell\nCOMMAND: echo hi\n",
        "ACTION: finish\nREASON: done\n",
    ]
    r, host, docker = _build_chat(tmp_path, script, containerize=True)
    r.sandbox_docker = None  # simulate "Docker not configured"
    r.run_task(str(tmp_path), "run echo hi")
    assert not docker.runner.calls
    assert host.calls, "without a docker executor the action must fall back to the host dispatcher"


def test_agent_containerize_routes_run_shell_to_docker(tmp_path):
    from harness.agent import AgentRunner, Task
    from harness.context.manager import ContextManager
    from harness.feedback.engine import FeedbackEngine
    from harness.guardrails.guardrail import Guardrail
    from harness.guardrails.hitl import HITL, FailClosedApprover
    from harness.guardrails.sandbox import Sandbox
    from harness.llm.mock import MockLLMClient
    from harness.memory.store import MemoryStore

    (tmp_path / "src").mkdir()
    c = Config.default()
    c.project_root = str(tmp_path)
    c.sandbox_containerize = True
    c.diff_preview = "never"
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(c, mem)
    host = RecordingDispatcher()
    docker = SandboxDockerExecutor(c, runner=FakeRunner(FakeCompletedProcess(stdout="container-out\n")))
    r = AgentRunner(
        MockLLMClient(["run.\nACTION: run_shell\nCOMMAND: echo hi\n", "ACTION: finish\nREASON: done\n"]),
        c,
        host,
        Guardrail(c),
        HITL(FailClosedApprover()),
        FeedbackEngine(c.test_timeout_s, c.stuck_repeat_n, c.stuck_no_progress_m, c.hint_history_lines),
        cm,
        sandbox=Sandbox(c),
        sandbox_docker=docker,
    )
    r.run(Task(str(tmp_path), "tests/t.py::test_a"))
    assert docker.runner.calls and not host.calls


# --- cli wiring: SandboxDockerExecutor constructed only when containerize ----


def test_cli_chat_constructs_docker_executor_when_containerize(tmp_path, monkeypatch):
    from harness.cli import main

    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    cfg_path = tmp_path / "harness.toml"
    cfg_path.write_text("[sandbox]\ncontainerize = true\n")
    captured = {}

    class FakeRunner:
        def __init__(self, *a, **k):
            captured["kwargs"] = k

        def run(self, repo, accept=None):
            return 0

    monkeypatch.setattr("harness.interactive.chat.ChatRunner", FakeRunner)
    main(["chat", "--repo", str(tmp_path), "--config", str(cfg_path)])
    sd = captured["kwargs"].get("sandbox_docker")
    assert isinstance(sd, SandboxDockerExecutor)


def test_cli_chat_no_containerize_passes_none(tmp_path, monkeypatch):
    from harness.cli import main

    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    captured = {}

    class FakeRunner:
        def __init__(self, *a, **k):
            captured["kwargs"] = k

        def run(self, repo, accept=None):
            return 0

    monkeypatch.setattr("harness.interactive.chat.ChatRunner", FakeRunner)
    main(["chat", "--repo", str(tmp_path)])
    assert captured["kwargs"].get("sandbox_docker") is None


# --- real-docker smoke (opt-in; never runs in the default suite) --------------


@pytest.mark.live
def test_run_shell_real_docker(tmp_path):
    """End-to-end against a real Docker daemon. Deselected by default (-m 'not live')."""
    c = cfg(tmp_path)
    res = SandboxDockerExecutor(c).run_shell(RunShell("echo hello-from-container"))
    assert res.ok and "hello-from-container" in res.stdout
