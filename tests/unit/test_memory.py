from harness.memory.store import MemoryStore


def test_notes_roundtrip(tmp_path):
    m = MemoryStore(str(tmp_path / "notes.md"), str(tmp_path / "log.jsonl"))
    assert m.load_notes() == ""
    m.save_notes("run tests with: pytest")
    assert "pytest" in m.load_notes()


def test_log_append_and_recent(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l.jsonl"))
    m.append_log({"task": "t1", "outcome": "SUCCESS"})
    m.append_log({"task": "t2", "outcome": "STUCK"})
    assert m.recent_log(1) == [{"task": "t2", "outcome": "STUCK"}]


def test_recent_log_absent_file_returns_empty(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "missing.jsonl"))
    assert m.recent_log(5) == []


def test_recent_log_skips_corrupt_lines(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_text(
        '{"task": "t1", "outcome": "SUCCESS"}\n'
        "this is not valid json\n"
        '{"task": "t2", "outcome": "STUCK"}\n'
    )
    m = MemoryStore(str(tmp_path / "n"), str(p))
    assert m.recent_log(10) == [
        {"task": "t1", "outcome": "SUCCESS"},
        {"task": "t2", "outcome": "STUCK"},
    ]
