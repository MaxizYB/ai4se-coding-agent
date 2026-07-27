import io

from harness.actions.protocol import ReadFile
from harness.feedback.types import FailureCategory, FailureReport
from harness.interactive.presenter import Presenter
from harness.tools.dispatcher import ToolResult


def _fb():
    return FailureReport(False, FailureCategory.LOGIC, ["t.test"],
                         "断言失败：修实现逻辑。", "tb", "4", "3", "sig", False)

def test_snapshot():
    out = io.StringIO()
    p = Presenter(out=out)
    p.welcome("/repo", accept="tests/t.py::test_a")
    p.show_prose("I'll read the file.")
    p.show_action(ReadFile("x.py"), ToolResult(True, "file contents here", "", 0))
    p.show_feedback(_fb())
    p.show_deny("out-of-scope")
    p.show_done("test green")
    p.show_turn_end("SUCCESS")
    text = out.getvalue()
    assert "/repo" in text and "accept: tests/t.py::test_a" in text
    assert "I'll read the file." in text
    assert "ReadFile" in text and "file contents here" in text
    assert "LOGIC" in text and "修实现逻辑" in text
    assert "denied" in text and "out-of-scope" in text
    assert "done" in text and "test green" in text
    assert "SUCCESS" in text

def test_show_prose_empty_is_noop():
    out = io.StringIO(); Presenter(out=out).show_prose("")
    assert out.getvalue() == ""


def test_show_diff_header_then_diff_text():
    out = io.StringIO()
    Presenter(out=out).show_diff(
        "src/foo.py", "--- src/foo.py\n+++ src/foo.py\n@@ -1 +1 @@\n-old\n+new\n"
    )
    text = out.getvalue()
    assert "proposed change: src/foo.py" in text  # header cites the path
    assert "+++ src/foo.py" in text               # diff body present
    assert "-old" in text and "+new" in text


def test_show_diff_truncates_long_diff_to_about_2000_chars():
    out = io.StringIO()
    huge = "+x" * 5000 + "\n"  # ~10k chars of additions
    Presenter(out=out).show_diff("a.py", huge)
    text = out.getvalue()
    assert "proposed change: a.py" in text
    assert len(text) <= 2200  # truncated to ~2000 (+ header/newline slack)


def test_show_report_renders_compact_block():
    out = io.StringIO()
    report = {
        "outcome": "SUCCESS",
        "files_changed": ["src/a.py", "src/b.py"],
        "commands_run": ["ruff check src", "pytest"],
        "tests": [
            {"selector": "tests/test_a.py", "green": True},
            {"selector": "tests/test_b.py", "green": False},
        ],
        "summary": "fixed and verified",
    }
    Presenter(out=out).show_report(report)
    text = out.getvalue()
    assert "=== task report ===" in text
    assert "outcome: SUCCESS" in text
    assert "files changed:" in text
    assert "src/a.py" in text and "src/b.py" in text
    assert "commands:" in text
    assert "ruff check src" in text and "pytest" in text
    assert "tests:" in text
    # selector surfaced with a green/red marker
    assert "tests/test_a.py" in text and "green" in text
    assert "tests/test_b.py" in text and "red" in text
    assert "summary: fixed and verified" in text


def test_show_report_handles_empty_lists():
    out = io.StringIO()
    report = {
        "outcome": "REPLIED",
        "files_changed": [],
        "commands_run": [],
        "tests": [],
        "summary": "",
    }
    Presenter(out=out).show_report(report)
    text = out.getvalue()
    assert "=== task report ===" in text
    assert "outcome: REPLIED" in text
