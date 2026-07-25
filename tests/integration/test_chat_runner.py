import io

from harness.config import Config
from harness.context.manager import ContextManager
from harness.feedback.engine import FeedbackEngine
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
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


def _runner(tmp_path, script, lines):
    cfg = Config.default()
    cfg.project_root = str(tmp_path)
    cfg.dangerous_shell_patterns = [r"rm\s+-rf?"]
    cfg.network_commands = ["pip install"]
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(cfg, mem)
    pres = Presenter(out=io.StringIO())
    r = ChatRunner(
        MockLLMClient(script),
        cfg,
        ToolDispatcher(cfg),
        Guardrail(cfg),
        HITL(FailClosedApprover()),
        FeedbackEngine(
            cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines
        ),
        cm,
        pres,
        input_fn=lambda _p: next(lines),
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
