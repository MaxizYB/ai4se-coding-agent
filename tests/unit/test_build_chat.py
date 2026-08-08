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
    assert "Request mode: inspect" in msgs[0].content
    assert "read-only repository inspection" in msgs[0].content
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


# --- C1/I3: @mention path traversal must not read outside the repo ---

def test_build_chat_mention_dotdot_traversal_rejected(tmp_path):
    # `@../../<secret>` must not escape the repo and inject outside content.
    # Nest repo two levels deep so `../..` resolves to a REAL outside file.
    repo = tmp_path / "work" / "repo"
    repo.mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "src" / "foo.py").write_text("print('inside')\n")
    secret = tmp_path / "hosts.conf"  # tmp_path/work/repo/../../hosts.conf == this
    secret.write_text("TOP_SECRET_HOSTS\n")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", "see @../../hosts.conf and @src/foo.py")]
    msgs = cm.build_chat(str(repo), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "TOP_SECRET_HOSTS" not in joined          # no traversal read
    assert "<@../../hosts.conf>" not in joined        # no injection slot
    assert "<@src/foo.py>" in joined and "print('inside')" in joined  # valid still works


def test_build_chat_mention_absolute_path_rejected(tmp_path):
    # `@/abs/path` must not read an absolute path outside the repo.
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.conf"
    outside.write_text("ABS_SECRET\n")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", f"see @{outside}")]
    msgs = cm.build_chat(str(repo), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "ABS_SECRET" not in joined
    assert "<@" not in joined


def test_build_chat_mention_sibling_traversal_rejected(tmp_path):
    # `@../sibling/x.yml` must not read a sibling dir outside the repo.
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "sibling").mkdir()
    (tmp_path / "sibling" / "x.yml").write_text("SIB_SECRET: 1\n")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", "see @../sibling/x.yml")]
    msgs = cm.build_chat(str(repo), None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "SIB_SECRET" not in joined
    assert "<@../sibling/x.yml>" not in joined


# --- I2: @mention of a binary file must be skipped gracefully ---

def test_build_chat_mention_binary_file_skipped(tmp_path):
    # A binary PNG (contains a NUL byte) must not crash build_chat and must
    # NOT be injected as garbled text.
    (tmp_path / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\xfa\xfe\xffIEND")
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    history = [Message("user", "see @pic.png")]
    msgs = cm.build_chat(str(tmp_path), None, history)  # no crash
    joined = "\n".join(x.content for x in msgs)
    assert "<@pic.png>" not in joined                    # skipped, no injection


# --- I1: compaction summary must survive the max_history bound ---

def test_build_chat_compaction_summary_survives_max_history_bound(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    cm.config.context_compact_threshold = 50
    cm.config.context_keep_recent = 6
    cm.config.max_history = 4  # keep_recent+1 (7) > max_history (4) -> naive slice drops summary
    history = [Message("assistant", "ACTION: edit_file\nPATH: src/a.py\n" + "x" * 100)]
    history += [Message("user", f"turn{i} " + "y" * 20) for i in range(7)]  # 8 total
    msgs = cm.build_chat("/repo", None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "[compacted history]" in joined          # summary survived the bound
