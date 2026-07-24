import re
from dataclasses import dataclass
from harness.feedback.types import FailureCategory, FailureReport
from harness.feedback.pytest_parser import parse_pytest_output
from harness.feedback.classifier import classify_run
from harness.feedback.strategy import strategy_hint
from harness.feedback.stuck import StuckDetector, signature_of

_EXPECTED = re.compile(r"assert\s+(?P<a>[^=]+?)\s*==\s*(?P<b>[^\s]+)")

class FeedbackEngine:
    def __init__(self, test_timeout_s: int, stuck_repeat_n: int,
                 stuck_no_progress_m: int, hint_history_lines: int):
        self.test_timeout_s = test_timeout_s
        self.hint_history_lines = hint_history_lines
        self.detector = StuckDetector(stuck_repeat_n, stuck_no_progress_m)

    def classify(self, tool_result) -> FailureReport:
        stderr = getattr(tool_result, "stderr", "")
        if getattr(tool_result, "exit_code", 0) == 124 or "TimeoutExpired" in stderr:
            hint = strategy_hint(FailureCategory.TIMEOUT, budget_s=self.test_timeout_s)
            sig = signature_of(["<timeout>"], FailureCategory.TIMEOUT)
            return FailureReport(False, FailureCategory.TIMEOUT, ["<timeout>"], hint,
                                 stderr[-self.hint_history_lines*80:], None, None, sig, False)
        run = parse_pytest_output(tool_result.exit_code, getattr(tool_result, "stdout", ""),
                                  stderr, getattr(tool_result, "junit_xml", ""))
        cat = classify_run(run)
        if cat is None:
            return FailureReport(True, None, [], "", "", None, None, "", False)
        failing = [f.nodeid for f in run.failures]
        msg = run.failures[0].message if run.failures else ""
        m = _EXPECTED.search(msg)
        expected = m.group("b").strip() if m else None
        actual = m.group("a").strip() if m else None
        hint = strategy_hint(cat, nodeid=failing[0] if failing else "",
                             expected=expected, actual=actual,
                             exc=run.failures[0].exc_type if run.failures else "")
        sig = signature_of(failing, cat)
        stuck = self.detector.update(sig, failing)
        excerpt = "\n".join((run.failures[0].traceback or "").splitlines()[-self.hint_history_lines:])
        return FailureReport(False, cat, failing, hint, excerpt, expected, actual, sig, stuck)
