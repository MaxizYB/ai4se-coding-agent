from harness.governance.task_report import TaskReport


def test_build_passthrough_outcome_and_summary():
    report = TaskReport.build([], "SUCCESS", "all green")
    assert report["outcome"] == "SUCCESS"
    assert report["summary"] == "all green"


def test_build_empty_events_yields_empty_lists():
    report = TaskReport.build([], "FINISH", "done")
    assert report["files_changed"] == []
    assert report["commands_run"] == []
    assert report["tests"] == []


def test_files_changed_dedup_preserves_first_seen_order():
    events = [
        {"kind": "file_changed", "path": "src/a.py"},
        {"kind": "file_changed", "path": "src/b.py"},
        {"kind": "file_changed", "path": "src/a.py"},  # dup -> dropped
        {"kind": "file_changed", "path": "src/c.py"},
        {"kind": "file_changed", "path": "src/b.py"},  # dup -> dropped
    ]
    report = TaskReport.build(events, "SUCCESS", "")
    assert report["files_changed"] == ["src/a.py", "src/b.py", "src/c.py"]


def test_commands_run_preserves_order_no_dedup():
    events = [
        {"kind": "shell", "cmd": "ls", "ok": True},
        {"kind": "shell", "cmd": "ls", "ok": True},   # same cmd twice -> kept
        {"kind": "shell", "cmd": "pwd", "ok": False},
    ]
    report = TaskReport.build(events, "FINISH", "")
    assert report["commands_run"] == ["ls", "ls", "pwd"]


def test_tests_collected_with_selector_and_green():
    events = [
        {"kind": "test", "selector": "tests/test_foo.py::test_add", "green": True},
        {"kind": "test", "selector": "tests/test_bar.py", "green": False},
    ]
    report = TaskReport.build(events, "SUCCESS", "")
    assert report["tests"] == [
        {"selector": "tests/test_foo.py::test_add", "green": True},
        {"selector": "tests/test_bar.py", "green": False},
    ]


def test_build_mixed_events_classifies_by_kind():
    events = [
        {"kind": "file_changed", "path": "src/a.py"},
        {"kind": "shell", "cmd": "ruff check src", "ok": True},
        {"kind": "test", "selector": "tests/test_a.py", "green": True},
        {"kind": "file_changed", "path": "src/a.py"},  # dup
        {"kind": "shell", "cmd": "pytest", "ok": True},
        {"kind": "test", "selector": "tests/test_b.py", "green": False},
    ]
    report = TaskReport.build(events, "SUCCESS", "fixed and verified")
    assert report["outcome"] == "SUCCESS"
    assert report["files_changed"] == ["src/a.py"]
    assert report["commands_run"] == ["ruff check src", "pytest"]
    assert report["tests"] == [
        {"selector": "tests/test_a.py", "green": True},
        {"selector": "tests/test_b.py", "green": False},
    ]
    assert report["summary"] == "fixed and verified"
