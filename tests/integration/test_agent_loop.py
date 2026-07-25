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


def test_tool_observation_fed_back_to_llm(tmp_path):
    # C2 regression: tool observations (read_file/list_dir/run_shell) must be
    # fed back into the LLM's next context. The old loop only stored
    # result.stdout/stderr in Turn.summary (display); the next context was
    # built from `ctx + [assistant raw] + last_fb` (only set for RunTests), so
    # a read_file result never reached the LLM. Mock scripts were
    # observation-independent so passed; under a real LLM the agent is blind.
    # This callable-mock inspects its incoming messages and asserts the
    # read_file content appears in a `user` message BEFORE emitting edit_file.
    _repo(tmp_path, "return a - b")
    marker = "MARKER_OBS_LINE_return_a_minus_b"
    (tmp_path / "src" / "foo.py").write_text(
        f"def add(a, b):\n    return a - b  # {marker}\n"
    )
    READ = "ACTION: read_file\nPATH: src/foo.py\n"
    EDIT_FROM_OBS = (
        f"ACTION: edit_file\nPATH: src/foo.py\n"
        f"<<<OLD\n    return a - b  # {marker}\n>>>OLD\n"
        f"<<<NEW\n    return a + b\n>>>NEW\n"
    )

    state = {"saw_observation": False}

    def script(messages):
        # Decide which action to emit based on how far we've progressed.
        user_msgs = [m.content for m in messages if m.role == "user"]
        # The observation message (a user-role message carrying tool output)
        # must appear before we commit to the edit. If C2 is missing, the only
        # user content is the initial prompt + feedback -- never the file body.
        if any(marker in c for c in user_msgs):
            state["saw_observation"] = True
            return EDIT_FROM_OBS
        if not any("edit_file" in c for c in [m.content for m in messages if m.role == "assistant"]):
            return READ
        return RT

    r = _runner(tmp_path, script, max_iterations=12).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    # The marker only appears in the read_file OBSERVATION (not the initial
    # prompt, not feedback). If it was observed, observation feedback works.
    assert state["saw_observation"], "read_file output never reached the LLM context"
    assert r.outcome == "SUCCESS"
    assert "return a + b" in (tmp_path / "src" / "foo.py").read_text()


def test_edits_diff_includes_newly_created_file(tmp_path):
    # I4 regression: `_diff` walked only `before.keys()` (files present at run
    # start), so a WriteFile creating a NEW file produced an EMPTY diff --
    # breaking US4 observability + §3.10 WebUI. The fix re-walks
    # allowed_write_dirs and emits an "added file" entry for any path not in
    # `before`.
    _repo(tmp_path, "return a - b")
    WRITE_NEW = (
        "ACTION: write_file\nPATH: src/newmod.py\n<<<\n"
        "def helper():\n    return 42\n>>>\n"
    )
    script = [WRITE_NEW, FIN]
    r = _runner(tmp_path, script).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    assert (tmp_path / "src" / "newmod.py").exists()
    assert "src/newmod.py" in r.edits_diff
    assert "def helper()" in r.edits_diff
