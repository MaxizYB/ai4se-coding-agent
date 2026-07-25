from harness.config import Config
from harness.context.manager import ContextManager, Message, locate_impl_module
from harness.feedback.types import FailureCategory, FailureReport
from harness.memory.store import MemoryStore


def _fb(cat=FailureCategory.LOGIC):
    return FailureReport(False, cat, ["t.test"], "HINTLINE", "tb", "4", "3", "sig", False)

def test_initial_context_has_system_and_protocol(tmp_path):
    (tmp_path/"tests").mkdir(); (tmp_path/"tests"/"t.py").write_text("def test_x(): assert 1==1\n")
    m = MemoryStore(str(tmp_path/"n"), str(tmp_path/"l"))
    cm = ContextManager(Config.default(), m); cm.config.project_root = str(tmp_path)
    msgs = cm.build_initial("tests/t.py")
    assert msgs[0].role == "system"
    assert any("ACTION:" in x.content for x in msgs)
    assert any("def test_x" in x.content for x in msgs)

def test_feedback_hint_is_emphasized(tmp_path):
    m = MemoryStore(str(tmp_path/"n"), str(tmp_path/"l"))
    cm = ContextManager(Config.default(), m); cm.config.project_root = str(tmp_path)
    msgs = cm.build([Message("assistant","old")], _fb())
    assert "HINTLINE" in msgs[-1].content

def test_history_is_bounded(tmp_path):
    m = MemoryStore(str(tmp_path/"n"), str(tmp_path/"l"))
    cm = ContextManager(Config.default(), m); cm.config.project_root = str(tmp_path)
    history = [Message("assistant", f"turn{i}") for i in range(10)]
    msgs = cm.build(history, _fb())
    joined = "\n".join(x.content for x in msgs)
    assert "turn9" in joined and "turn0" not in joined

def test_locate_impl_module_traces_import(tmp_path):
    (tmp_path/"src").mkdir(); (tmp_path/"src"/"foo.py").write_text("def add(a,b): return a-b\n")
    (tmp_path/"tests").mkdir(); (tmp_path/"tests"/"test_foo.py").write_text("from foo import add\n")
    assert locate_impl_module(str(tmp_path/"tests"/"test_foo.py")) == "src/foo.py"
