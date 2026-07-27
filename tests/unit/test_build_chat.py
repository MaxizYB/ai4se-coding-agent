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


def test_build_chat_compacts_over_threshold_history(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    cm.config.context_compact_threshold = 50
    cm.config.context_keep_recent = 2
    cm.config.max_history = 8
    history = [
        Message("assistant", "ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\nx\n>>>OLD"),
        Message("user", "OBSERVATION: done " + "y" * 200),
        Message("user", "recent-q"),
        Message("assistant", "recent-a"),
    ]
    msgs = cm.build_chat("/repo", None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "[compacted history]" in joined  # compaction fired
    assert "edit_file" in joined  # dropped action preserved as a fact
    assert "recent-q" in joined and "recent-a" in joined  # recent kept verbatim


def test_build_chat_loads_agents_md_project_memory(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Always use ruff for linting.\n")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat(str(tmp_path), None, [])
    joined = "\n".join(x.content for x in msgs)
    assert "Project memory (AGENTS.md):" in joined
    assert "Always use ruff for linting." in joined


def test_build_chat_without_agents_md_omits_project_memory(tmp_path):
    # No AGENTS.md present in repo dir.
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat(str(tmp_path), None, [])
    joined = "\n".join(x.content for x in msgs)
    assert "Project memory (AGENTS.md):" not in joined


def test_build_chat_includes_both_agents_md_and_notes(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Convention: use dataclasses.\n")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    m.save_notes("run tests with: pytest")
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat(str(tmp_path), None, [])
    joined = "\n".join(x.content for x in msgs)
    assert "Project memory (AGENTS.md):" in joined
    assert "Convention: use dataclasses." in joined
    assert "Project notes:" in joined
    assert "pytest" in joined


def test_build_chat_empty_agents_md_omits_project_memory(tmp_path):
    (tmp_path / "AGENTS.md").write_text("")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat(str(tmp_path), None, [])
    joined = "\n".join(x.content for x in msgs)
    assert "Project memory (AGENTS.md):" not in joined


def test_build_chat_pulls_mentioned_file_into_context(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("print('hi')\n")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", "look at @src/foo.py")]
    msgs = cm.build_chat(str(tmp_path), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "<@src/foo.py>" in joined
    assert "print('hi')" in joined


def test_build_chat_mention_missing_file_skipped_no_crash(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", "check @src/missing.py")]
    msgs = cm.build_chat(str(tmp_path), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "<@src/missing.py>" not in joined


def test_build_chat_mention_oversized_file_truncated(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "big.py").write_text("x" * 200)
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    cm.config.context_mention_max_chars = 50
    history = [Message("user", "see @src/big.py")]
    msgs = cm.build_chat(str(tmp_path), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "<@src/big.py>" in joined
    assert "[truncated, 200 chars total]" in joined


def test_build_chat_non_file_mention_token_not_matched(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", "hi @user how are you")]
    msgs = cm.build_chat(str(tmp_path), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "<@" not in joined
