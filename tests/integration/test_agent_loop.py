from harness.agent import AgentRunner, Task
from harness.config import Config
from harness.context.manager import ContextManager
from harness.feedback.engine import FeedbackEngine
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.guardrails.sandbox import Sandbox
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
        sandbox=Sandbox(cfg),
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
    # C2 regression: tool observations (read_file/list_dir/run_shell/run_tests)
    # must be fed back into the LLM's next context as a DISTINCT user message.
    # The old loop stored result.stdout/stderr only in Turn.summary (display);
    # the next context was ctx + [assistant raw] + last_fb (only set for
    # RunTests), so a read_file result never reached the LLM. Mock scripts were
    # observation-independent so passed; under a real LLM the agent is blind.
    #
    # This test targets the OBSERVATION-FEEDBACK path SPECIFICALLY -- not the
    # ContextManager.build_initial injection (which pre-loads the located impl
    # module). The previous version of this test read src/foo.py and checked
    # `marker in user_msgs`; that was tautological/fragile: build_initial
    # injects foo.py's body into the initial prompt, so the marker was already
    # present on iteration 1 regardless of the C2 fix (a latent test_selector
    # path-resolution bug currently masks this, but the test must not depend on
    # that bug). Two independent safeguards make this assertion bulletproof:
    #   (1) Option A -- assert a user message that BOTH starts with the
    #       observation prefix ("OBSERVATION:") AND carries the marker. The
    #       initial prompt and FEEDBACK messages do NOT start with that prefix.
    #   (2) Option B -- read a SEPARATE helper file that build_initial never
    #       injects (it is not the impl module located from the test imports),
    #       so the marker can ONLY reach the LLM via the read_file observation.
    _repo(tmp_path, "return a - b")
    # Unique marker absent from src/foo.py, the test file, and any
    # build_initial-injected path. Helper is not imported by the test, so
    # locate_impl_module never resolves it -> never pre-injected.
    marker = "UNIQUE_OBS_TOKEN_7c3f9a_read_helper_body"
    (tmp_path / "src" / "helper.py").write_text(
        f"# project scratch\nHINT = {marker!r}\n"
    )
    READ_HELPER = "ACTION: read_file\nPATH: src/helper.py\n"
    EDIT_FROM_OBS = (
        "ACTION: edit_file\nPATH: src/foo.py\n"
        "<<<OLD\n    return a - b\n>>>OLD\n"
        "<<<NEW\n    return a + b\n>>>NEW\n"
    )

    state = {"saw_observation_msg": False}

    def script(messages):
        # Detect the C2 observation message: a user-role message that BOTH
        # starts with the observation prefix AND carries the unique marker.
        # Without the C2 append, no message ever starts with "OBSERVATION:".
        for m in messages:
            if m.role == "user" and m.content.startswith("OBSERVATION:") and marker in m.content:
                state["saw_observation_msg"] = True
                break
        # Phase 1: read the helper file (no observation seen yet).
        if not state["saw_observation_msg"]:
            return READ_HELPER
        # Phase 2: once the observation reached us, emit the fix edit (once).
        assistant = [m.content for m in messages if m.role == "assistant"]
        if not any("edit_file" in c for c in assistant):
            return EDIT_FROM_OBS
        # Phase 3: verify green.
        return RT

    r = _runner(tmp_path, script, max_iterations=12).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    assert state["saw_observation_msg"], (
        "no user message starting with 'OBSERVATION:' and carrying the read_file "
        "marker reached the LLM -- tool observation was not fed back (C2 broken)"
    )
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


def test_finish_terminates_without_dispatching_to_tools(tmp_path):
    # M3 regression: Finish must terminate the loop WITHOUT being handed to
    # ToolDispatcher. The old code dispatched Finish (falling through every
    # isinstance arm in dispatcher.execute) and got back the catch-all
    # `unknown action Finish` ToolResult, which then surfaced in the turn
    # summary AND polluted the SSE/WebUI stream with a spurious error. The
    # fix reorders the loop so Finish short-circuits termination before the
    # executor is ever called.
    _repo(tmp_path, "return a - b")
    # RT fails (no edit applied); Finish then terminates the loop. Without
    # the fix, the Finish turn's summary is "unknown action Finish".
    r = _runner(tmp_path, [RT, FIN]).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add")
    )
    finish_turns = [t for t in r.turns if t.action == "Finish"]
    assert finish_turns, "a Finish action must record a turn"
    assert "unknown action" not in finish_turns[0].summary, (
        f"Finish was dispatched to ToolDispatcher (summary="
        f"{finish_turns[0].summary!r}); it must terminate without dispatch"
    )
