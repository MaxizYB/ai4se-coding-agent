from harness.config import Config
from harness.context.manager import ContextManager, Message
from harness.memory.store import MemoryStore


def test_build_chat_has_system_repo_and_accept(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat("/my/repo", "tests/t.py::test_a", [])
    assert msgs[0].role == "system"
    assert "/my/repo" in msgs[0].content
    assert "tests/t.py::test_a" in msgs[0].content
    assert "ACTION:" in msgs[0].content  # protocol reminder


def test_build_chat_no_accept_omits_acceptance(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat("/repo", None, [])
    assert "Acceptance" not in msgs[0].content


def test_build_chat_includes_notes_and_bounds_history(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    m.save_notes("run tests with: pytest")
    cm = ContextManager(Config.default(), m)
    cm.config.max_history = 2
    history = [Message("user", f"turn{i}") for i in range(5)]
    msgs = cm.build_chat("/repo", None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "pytest" in joined  # notes present
    assert "turn4" in joined and "turn0" not in joined  # bounded to last 2
