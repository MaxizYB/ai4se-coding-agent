from harness.config import Config
from harness.memory.compactor import Compactor
from harness.types import Message


def _hist(*pairs: tuple[str, str]) -> list[Message]:
    return [Message(role, content) for role, content in pairs]


def _cfg(threshold: int = 6000, keep_recent: int = 6) -> Config:
    c = Config.default()
    c.context_compact_threshold = threshold
    c.context_keep_recent = keep_recent
    return c


def test_under_threshold_returns_same_list_identity():
    history = _hist(("user", "hello"), ("assistant", "hi"))
    result = Compactor(_cfg()).maybe_compact(history)
    assert result is history  # unchanged identity, not a copy


def test_empty_history_unchanged():
    result = Compactor(_cfg()).maybe_compact([])
    assert result == []


def test_single_message_unchanged():
    history = _hist(("user", "x" * 10))
    result = Compactor(_cfg()).maybe_compact(history)
    assert result is history


def test_over_threshold_compacts_into_one_system_plus_recent():
    cfg = _cfg(threshold=100, keep_recent=2)
    old = [
        Message(
            "assistant",
            "let me edit the file\nACTION: edit_file\nPATH: src/foo.py\n"
            "<<<OLD\nold\n>>>OLD\n<<<NEW\nnew\n>>>NEW",
        ),
        Message("user", "OBSERVATION: edit applied ok"),
        Message("user", "FEEDBACK: tests still failing somehow"),
        Message("assistant", "plain reply with no action " + "z" * 200),
    ]
    recent = [Message("user", "recent1"), Message("assistant", "recent2")]
    history = old + recent
    result = Compactor(cfg).maybe_compact(history)
    assert result is not history
    assert len(result) == 3  # 1 compacted system + 2 kept
    assert result[0].role == "system"
    assert result[0].content.startswith("[compacted history]")
    # the dropped edit_file action is preserved as a structured fact line
    assert "assistant: edit_file PATH=src/foo.py" in result[0].content
    # recent turns are kept verbatim (same objects)
    assert result[1] is recent[0]
    assert result[2] is recent[1]


def test_boundary_exactly_threshold_is_unchanged():
    cfg = _cfg(threshold=50, keep_recent=6)
    history = _hist(("user", "a" * 25), ("assistant", "b" * 25))
    assert sum(len(m.content) for m in history) == 50
    result = Compactor(cfg).maybe_compact(history)
    assert result is history


def test_boundary_threshold_plus_one_compacts():
    cfg = _cfg(threshold=50, keep_recent=1)
    history = _hist(("user", "a" * 25), ("assistant", "b" * 26))
    assert sum(len(m.content) for m in history) == 51
    result = Compactor(cfg).maybe_compact(history)
    assert result is not history
    assert result[0].role == "system"
    assert result[0].content.startswith("[compacted history]")
    assert result[-1] is history[-1]  # last turn kept verbatim


def test_keep_recent_ge_len_history_unchanged_even_over_threshold():
    cfg = _cfg(threshold=1, keep_recent=10)  # over threshold, but keep >= len
    history = _hist(("user", "a"), ("assistant", "b"))
    result = Compactor(cfg).maybe_compact(history)
    assert result is history


def test_observation_and_feedback_facts_truncated_to_80_chars_single_line():
    cfg = _cfg(threshold=10, keep_recent=1)
    long_obs = "OBSERVATION: " + ("x" * 200)
    history = [Message("user", long_obs), Message("assistant", "kept")]
    result = Compactor(cfg).maybe_compact(history)
    body = result[0].content.split("[compacted history]\n", 1)[1]
    fact = body.splitlines()[0]
    assert fact.startswith("OBSERVATION:")
    assert len(fact) <= 80
    assert "\n" not in fact


def test_else_branch_collapses_newlines_and_truncates():
    cfg = _cfg(threshold=10, keep_recent=1)
    multi = "line one\nline two\nline three " + ("q" * 200)
    history = [Message("assistant", multi), Message("user", "kept")]
    result = Compactor(cfg).maybe_compact(history)
    body = result[0].content.split("[compacted history]\n", 1)[1]
    fact = body.splitlines()[0]
    assert "\n" not in fact
    assert len(fact) <= 80


def test_fact_action_match_is_line_anchored_not_substring():
    # M6: "ACTION:" appearing mid-line (e.g. quoted inside a FEEDBACK message)
    # must NOT be mis-classified as a real action line.
    cfg = _cfg(threshold=10, keep_recent=1)
    content = "FEEDBACK: the docs say ACTION: finish ends the turn " + ("x" * 200)
    history = [Message("user", content), Message("assistant", "kept")]
    result = Compactor(cfg).maybe_compact(history)
    body = result[0].content.split("[compacted history]\n", 1)[1]
    fact = body.splitlines()[0]
    assert fact.startswith("FEEDBACK:")      # treated as plain text, not an action
    assert not fact.startswith("user: ")      # not given the action-fact prefix
    assert "PATH=" not in fact                # no structured keys extracted


def test_compacted_history_summary_preserved_on_recompaction():
    # M3: when a prior [compacted history] summary ages into "old" and is
    # re-compacted, it must NOT be crushed to the 80-char fact cap.
    cfg = _cfg(threshold=10, keep_recent=1)
    prior = "[compacted history]\n" + ("assistant: edit_file PATH=src/foo.py\n" * 5) + ("detail " * 60)
    assert len(prior) > 500
    history = [Message("system", prior), Message("user", "kept")]
    result = Compactor(cfg).maybe_compact(history)
    assert result[0].content.startswith("[compacted history]")
    body = result[0].content.split("[compacted history]\n", 1)[1]
    first_fact = body.splitlines()[0]
    assert len(first_fact) > 80               # preserved well past the old 80 cap
    assert "edit_file" in first_fact          # content actually preserved
