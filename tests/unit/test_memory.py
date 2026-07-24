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
