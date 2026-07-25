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
