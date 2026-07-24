from pathlib import Path

from harness.feedback.engine import FeedbackEngine
from harness.feedback.types import FailureCategory

FIX = Path(__file__).parent.parent / "fixtures"
def _xml(n): return (FIX / n).read_text()

class TR:  # minimal duck-typed tool result
    def __init__(self, exit_code, junit, stderr=""): self.exit_code=exit_code; self.junit_xml=junit; self.stderr=stderr; self.stdout=""

def test_green_report():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(0, _xml("green.xml")))
    assert r.is_green and r.category is None and r.hint == "" and not r.stuck

def test_logic_report_has_hint_and_signature():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(1, _xml("assertion.xml")))
    assert r.category is FailureCategory.LOGIC
    assert "断言" in r.hint and r.signature and r.failing == ["t.Tests.test_add"]

def test_env_report():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(2, _xml("import_err.xml")))
    assert r.category is FailureCategory.ENV and "不要改断言" in r.hint

def test_stuck_flag_after_repeats():
    eng = FeedbackEngine(30, 3, 10, 8)
    reports = [eng.classify(TR(1, _xml("assertion.xml"))) for _ in range(3)]
    assert not reports[0].stuck and not reports[1].stuck and reports[2].stuck is True

def test_timeout_report():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(124, "", stderr="subprocess.TimeoutExpired: 30"))
    assert r.category is FailureCategory.TIMEOUT
