from harness.agent import AgentRunner, Task
from harness.config import Config
from harness.context.manager import ContextManager
from harness.feedback.engine import FeedbackEngine
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.llm.mock import MockLLMClient
from harness.memory.store import MemoryStore
from harness.tools.dispatcher import ToolDispatcher


def _repo(tmp_path, body):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text(f"def add(a, b):\n    {body}\n")
    (tmp_path / "tests" / "test_foo.py").write_text(
        "from foo import add\n\ndef test_add():\n    assert add(2,2) == 4\n"
    )
    # The dispatcher runs a real pytest subprocess with cwd=project_root and
    # does not inject PYTHONPATH; without this conftest, `from foo import add`
    # raises ModuleNotFoundError (src/ is not on sys.path). This is pure
    # test-fixture plumbing -- the production harness code is unchanged.
    (tmp_path / "conftest.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))\n"
    )


def _runner(tmp_path, script, **overrides):
    cfg = Config.default()
    cfg.project_root = str(tmp_path)
    cfg.dangerous_shell_patterns = [r"rm\s+-rf?"]
    cfg.network_commands = ["pip install"]
    for k, v in overrides.items():
        setattr(cfg, k, v)
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(cfg, mem)
    return AgentRunner(
        MockLLMClient(script),
        cfg,
        ToolDispatcher(cfg),
        Guardrail(cfg),
        HITL(FailClosedApprover()),
        FeedbackEngine(
            cfg.test_timeout_s,
            cfg.stuck_repeat_n,
            cfg.stuck_no_progress_m,
            cfg.hint_history_lines,
        ),
        cm,
    )


EDIT = (
    "ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n"
    "<<<NEW\n    return a + b\n>>>NEW\n"
)
RT = "ACTION: run_tests\nARGS: tests/test_foo.py::test_add\n"
FIN = "ACTION: finish\nREASON: green\n"


def test_green_path_closes_feedback_loop(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, [RT, EDIT, RT, FIN]).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    assert r.outcome == "SUCCESS"
    # the edit happened AFTER a failing run_tests (feedback drove the change)
    actions = [t.action for t in r.turns]
    assert "RunTests" in actions and "EditFile" in actions
    assert actions.index("EditFile") > actions.index("RunTests")
    assert "return a + b" in (tmp_path / "src" / "foo.py").read_text()


def test_stuck_termination(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, [RT], stuck_repeat_n=3, max_iterations=99).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    assert r.outcome == "STUCK"


def test_budget_exhausted(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, [RT], stuck_repeat_n=99, stuck_no_progress_m=99, max_iterations=2).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    assert r.outcome == "BUDGET_EXHAUSTED"


def test_dangerous_action_denied_by_fail_closed(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, ["ACTION: run_shell\nCOMMAND: rm -rf /\n", FIN]).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    decisions = [t.decision for t in r.turns]
    assert "Deny" in decisions  # fail-closed HITL denied the rm
    assert (tmp_path / "src" / "foo.py").read_text().count("return") == 1  # file untouched by rm
