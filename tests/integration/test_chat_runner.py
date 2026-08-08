import io

from harness.config import Config
from harness.context.manager import ContextManager
from harness.feedback.engine import FeedbackEngine
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover, StubApprover
from harness.guardrails.sandbox import Sandbox
from harness.interactive.chat import ChatRunner
from harness.interactive.presenter import Presenter
from harness.llm.mock import MockLLMClient
from harness.memory.store import MemoryStore
from harness.tools.dispatcher import ToolDispatcher


def _repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "tests" / "test_foo.py").write_text(
        "from foo import add\n\ndef test_add():\n    assert add(2,2)==4\n"
    )
    (tmp_path / "conftest.py").write_text(
        "import os,sys\nsys.path.insert(0,os.path.join(os.path.dirname(__file__),'src'))\n"
    )


def _runner(tmp_path, script, lines, *, hitl=None, dangerous_patterns=None, sandbox=None, **overrides):
    cfg = Config.default()
    cfg.project_root = str(tmp_path)
    # `is not None` (not `or`) so an explicit empty list disables the dangerous
    # patterns -- required to prove the SANDBOX (not the guardrail) denies.
    cfg.dangerous_shell_patterns = (
        dangerous_patterns if dangerous_patterns is not None else [r"rm\s+-rf?"]
    )
    cfg.network_commands = ["pip install"]
    # G3: these scenarios test the feedback/sandbox/accept loops (not diff
    # approval) under a fail-closed approver; opt out of the write-before-apply
    # gate so writes still apply. Tests exercising the gate pass diff_preview=.
    cfg.diff_preview = "never"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(cfg, mem)
    pres = Presenter(out=io.StringIO())
    r = ChatRunner(
        MockLLMClient(script),
        cfg,
        ToolDispatcher(cfg),
        Guardrail(cfg),
        hitl or HITL(FailClosedApprover()),
        FeedbackEngine(
            cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines
        ),
        cm,
        pres,
        input_fn=lambda _p: next(lines),
        sandbox=sandbox if sandbox is not None else Sandbox(cfg),
    )
    return r, pres


EDIT = (
    "ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n"
    "<<<NEW\n    return a + b\n>>>NEW\n"
)
RT = "ACTION: run_tests\nARGS: tests/test_foo.py::test_add\n"
FIN = "ACTION: finish\nREASON: test green\n"


def test_chat_read_edit_runtests_finish(tmp_path):
    _repo(tmp_path)
    script = [
        "Reading foo.\nACTION: read_file\nPATH: src/foo.py\n",
        "Fixing it.\n" + EDIT,
        "Verifying.\n" + RT,
        "Done.\n" + FIN,
    ]
    lines = iter(["make the test pass", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "Reading foo." in text and "Fixing it." in text and "Verifying." in text
    assert "ReadFile" in text and "EditFile" in text and "RunTests" in text
    assert "done" in text and "test green" in text
    with open(tmp_path / "src" / "foo.py") as f:
        assert "return a + b" in f.read()


def test_chat_accept_green_after_edit(tmp_path):
    _repo(tmp_path)
    script = ["Fix.\n" + EDIT, "Check.\n" + RT, FIN]  # FIN unused if accept stops first
    lines = iter(["fix", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept="tests/test_foo.py::test_add")
    assert "SUCCESS" in pres.out.getvalue()  # accept green stops with SUCCESS


def test_slash_clear_and_exit(tmp_path):
    _repo(tmp_path)
    lines = iter(["/clear", "/exit"])
    r, pres = _runner(tmp_path, [], lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "cleared" in text and "bye" in text


# #8: the `/tests` slash command must NOT bypass the sandbox gate. With
# containerize on but no docker executor wired, it fails closed (denied) instead
# of running on the host dispatcher.
def test_slash_tests_routed_through_sandbox_gate(tmp_path):
    _repo(tmp_path)
    lines = iter(["/tests tests/test_foo.py", "/exit"])
    r, pres = _runner(tmp_path, [], lines, sandbox_containerize=True)
    # _runner wires Sandbox(cfg) but NO sandbox_docker -> containerize + no
    # executor -> fail-closed (Deny), never reaching the host dispatcher.
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "denied" in text
    assert "containerize" in text


# --- C1: ChatRunner must route AskHuman through the injected HITL, never
# through global input(). In task mode (FailClosedApprover) a dangerous
# action must fail-closed WITHOUT prompting; in chat mode the injected
# Approver decides. -----------------------------------------------------------

DANGER = "ACTION: run_shell\nCOMMAND: rm -rf /\n"


def test_task_mode_dangerous_action_failclosed(tmp_path, monkeypatch):
    # If the loop ever falls back to global input() it raises (proving no
    # prompt), and would hang/EOF in piped CI. FailClosedApprover must deny.
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("input called in non-interactive mode")
        ),
    )
    _repo(tmp_path)
    script = ["Removing.\n" + DANGER, "bye.\n" + FIN]
    r, pres = _runner(tmp_path, script, iter([]), hitl=HITL(FailClosedApprover()))
    rc = r.run_task(str(tmp_path), goal="clean up", accept=None)
    text = pres.out.getvalue()
    assert rc == 0                      # FINISH after deny; no hang, no prompt
    assert "denied" in text             # dangerous action fail-closed
    assert "rm -rf /" in text           # deny reason cites the command


def _chat_stub_runner(tmp_path, approve, monkeypatch):
    # A safe sentinel command that still trips a dangerous pattern so the
    # guardrail returns AskHuman (exercising the HITL seam) without ever
    # running a destructive shell.
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("real input called")),
    )
    _repo(tmp_path)
    script = [
        "Sentinel.\nACTION: run_shell\nCOMMAND: echo DANGER_TOKEN\n",
        "bye.\n" + FIN,
    ]
    lines = iter(["do the thing", "/exit"])
    r, pres = _runner(
        tmp_path,
        script,
        lines,
        hitl=HITL(StubApprover(approve)),
        dangerous_patterns=[r"DANGER_TOKEN"],
    )
    r.run(str(tmp_path), accept=None)
    return pres.out.getvalue()


def test_chat_mode_dangerous_stub_approver_allows(tmp_path, monkeypatch):
    text = _chat_stub_runner(tmp_path, True, monkeypatch)
    assert "denied" not in text         # StubApprover(True) allowed the action
    assert "RunShell" in text           # action was executed (shown by presenter)


def test_chat_mode_dangerous_stub_approver_denies(tmp_path, monkeypatch):
    text = _chat_stub_runner(tmp_path, False, monkeypatch)
    assert "denied" in text             # StubApprover(False) denied the action
    assert "RunShell" not in text       # action was NOT executed


# --- I1: in run_task, --accept requires the accept test to go green; a
# Finish without prior accept-green must return rc 1 + a clear message. -------

def test_run_task_accept_not_verified_returns_1(tmp_path):
    _repo(tmp_path)
    script = ["done.\n" + FIN]          # Finish WITHOUT running the accept test
    r, pres = _runner(tmp_path, script, iter([]))
    rc = r.run_task(
        str(tmp_path), goal="fix it", accept="tests/test_foo.py::test_add"
    )
    text = pres.out.getvalue()
    assert rc == 1                      # accept never went green
    assert "not verified" in text       # explicit message citing the selector
    assert "tests/test_foo.py::test_add" in text


def test_finish_terminates_without_dispatching(tmp_path):
    # Fix A: Finish is a TERMINAL signal — must NOT reach the dispatcher.
    # The ToolDispatcher's catch-all returns "unknown action Finish", which a
    # real LLM sees as noise. The mock-driven suite missed this because mock
    # scripts always emitted Finish after a green run_tests (which returned
    # SUCCESS first, never exercising the Finish branch). The NEGATIVE
    # assertion (`"unknown action" not in text`) is what makes this a real gate.
    _repo(tmp_path)
    script = ["I'm a coding agent here to help.\nACTION: finish\nREASON: answered\n"]
    lines = iter(["who are you?", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "answered" in text           # Finish reason shown
    assert "done" in text
    assert "unknown action" not in text  # Finish was NOT dispatched


def test_pure_prose_reply_ends_turn_without_finish(tmp_path):
    # Conversational fix: a pure-prose reply (no ACTION) must END the turn and
    # return to the user prompt — NOT internally re-prompt the agent until it
    # emits Finish. The old `continue` made the agent print "done/FINISH" after
    # every message, so the user could not hold a conversation. Claude/Codex
    # model: text with no tool call = turn ends. Mock scripts always emitted
    # an ACTION every turn, so this was invisible until live use.
    _repo(tmp_path)
    script = [
        "I can read and edit files and run tests. What do you need?",  # pure prose, NO ACTION
        "Reading foo.\nACTION: read_file\nPATH: src/foo.py\n",
        "Done.\nACTION: finish\nREASON: read it\n",
    ]
    lines = iter(["what can you do?", "read foo.py", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    # Turn 1 was a REPLY: prose shown, but NO "done"/"FINISH" status noise.
    assert "I can read and edit files" in text
    assert "--- REPLIED ---" not in text        # REPLIED is silent (no status line)
    # Turn 2 acted (read_file) and finished normally.
    assert "ReadFile" in text
    assert "Reading foo." in text


def test_informational_request_blocks_model_write(tmp_path):
    _repo(tmp_path)
    script = [
        "I found the likely issue.\n" + EDIT,
        "I will make the source change now.\n" + EDIT,
        "The repository is unchanged; ask for a concrete fix when needed.",
    ]
    lines = iter(["仓库里面有什么", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept="tests/test_foo.py::test_add")
    text = pres.out.getvalue()
    assert text.count("write blocked") == 2
    assert "proposed change" not in text
    assert "return a - b" in (tmp_path / "src" / "foo.py").read_text()


# --- G2: Sandbox gate fires AFTER the guardrail Allow. The guardrail is made
# permissive here (no dangerous patterns; tests/ admitted to the write SCOPE)
# so the Sandbox is the SOLE gate that can deny these actions -- proving the
# gate is wired into the loop and runs after the soft guardrail allows, not
# instead of it. If the gate were absent, `rm -rf /` would EXECUTE on the host
# and tests/x.py would be WRITTEN to disk. -------------------------------------

def test_sandbox_gate_denies_dangerous_shell_safe_shell_and_out_of_root_write(tmp_path):
    _repo(tmp_path)
    # Guardrail permissive: no dangerous patterns + tests/ in allowed_write_dirs,
    # so only the Sandbox (default write_roots=["src"], denylist has rm -rf /)
    # can deny. The deny reason must come from the sandbox, not the guardrail.
    script = [
        "Nuke.\nACTION: run_shell\nCOMMAND: rm -rf /\n",            # sandbox denylist hit
        "List.\nACTION: run_shell\nCOMMAND: ls\n",                   # sandbox allows -> runs
        "Write.\nACTION: write_file\nPATH: tests/x.py\n<<<\nx\n>>>\n",  # outside write_roots
        "Done.\nACTION: finish\nREASON: done\n",
    ]
    r, pres = _runner(
        tmp_path, script, iter([]),
        dangerous_patterns=[],
        allowed_write_dirs=["src", "tests"],
    )
    rc = r.run_task(str(tmp_path), goal="exercise sandbox gate", accept=None)
    text = pres.out.getvalue()
    # (1) rm -rf / denied, and the reason is the SANDBOX's (contains "sandbox").
    assert "denied" in text
    assert "sandbox" in text.lower()
    # (2) the safe `ls` ran -- dispatcher executed it (RunShell surfaced).
    assert "RunShell" in text
    # (3) tests/x.py was NOT written (sandbox denied the out-of-root write).
    assert not (tmp_path / "tests" / "x.py").exists()
    assert rc == 0  # Finish after the denies -> FINISH -> rc 0


# --- G3: DiffPreviewer + approval gate (write-before-apply). In "ask" mode the
# approver decides; a deny skips the write (file unchanged). "never" applies
# silently and NEVER consults the approver (proven by wiring a denying one). ---

WRITE = (
    "ACTION: write_file\nPATH: src/written.py\n<<<\n"
    "def g():\n    return 9\n>>>\n"
)


def test_chat_diff_preview_ask_stub_approve_applies(tmp_path):
    _repo(tmp_path)
    script = ["Writing.\n" + WRITE, "bye.\n" + FIN]
    lines = iter(["write a module", "/exit"])
    r, pres = _runner(
        tmp_path, script, lines,
        hitl=HITL(StubApprover(True)),
        diff_preview="ask",
    )
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "proposed change: src/written.py" in text           # diff shown
    assert (tmp_path / "src" / "written.py").exists()          # applied
    assert "return 9" in (tmp_path / "src" / "written.py").read_text()


def test_chat_diff_preview_ask_stub_deny_skips(tmp_path):
    _repo(tmp_path)
    script = ["Writing.\n" + WRITE, "bye.\n" + FIN]
    lines = iter(["write a module", "/exit"])
    r, pres = _runner(
        tmp_path, script, lines,
        hitl=HITL(StubApprover(False)),
        diff_preview="ask",
    )
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    # #6: do NOT print a proposed diff for a write that will be denied — show the
    # diff only once the approver says yes. A denied write surfaces only "skipped".
    assert "proposed change" not in text
    assert not (tmp_path / "src" / "written.py").exists()      # NOT applied
    assert "skipped" in text                                   # skip surfaced explicitly


def test_chat_diff_preview_never_applies_silently_without_asking(tmp_path):
    # "never" must NOT consult the approver at all: wire a DENYING approver and
    # prove the write still lands + no diff is shown.
    _repo(tmp_path)
    script = ["Writing.\n" + WRITE, "bye.\n" + FIN]
    lines = iter(["write a module", "/exit"])
    r, pres = _runner(
        tmp_path, script, lines,
        hitl=HITL(StubApprover(False)),
        diff_preview="never",
    )
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "proposed change" not in text                      # no preview shown
    assert (tmp_path / "src" / "written.py").exists()         # applied silently


# --- G4: TaskReport — structured end-of-task summary. After a turn that acted
# (edit + run_tests + finish), the rendered report must surface the edited file
# path and the test entry. A pure-prose REPLIED turn with NO tool events must
# NOT emit a report block (avoids noise on simple Q&A). ----------------------

def test_chat_report_shown_after_edit_runtests_finish(tmp_path):
    _repo(tmp_path)
    script = [
        "Reading foo.\nACTION: read_file\nPATH: src/foo.py\n",
        "Fixing it.\n" + EDIT,
        "Verifying.\n" + RT,
        "Done.\n" + FIN,
    ]
    lines = iter(["make the test pass", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "task report" in text and "outcome:" in text          # report emitted at FINISH
    assert "outcome: FINISH" in text
    assert "src/foo.py" in text                    # edited file surfaced
    assert "tests/test_foo.py::test_add" in text   # test entry surfaced
    assert "test green" in text                    # Finish reason -> summary


def test_chat_no_report_on_pure_prose_reply(tmp_path):
    # A pure-prose REPLIED turn with no file/shell/test events must NOT emit a
    # report block. The report is for task turns that DID something.
    _repo(tmp_path)
    script = [
        "I can read and edit files. What do you need?",  # pure prose, NO ACTION
        "Done.\nACTION: finish\nREASON: read it\n",
    ]
    lines = iter(["what can you do?", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    # The REPLIED turn (first) had no events -> no report block. Only the later
    # FINISH turn (also no file/shell/test events) might or might not show one,
    # but the FIRST turn's reply must NOT carry a report. We assert the prose is
    # shown and that there is at most the FINISH-turn report. The key contract:
    # a REPLIED turn never prints "outcome: REPLIED".
    assert "I can read and edit files" in text
    assert "outcome: REPLIED" not in text
