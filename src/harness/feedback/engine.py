import re

from harness.feedback.classifier import classify_run
from harness.feedback.pytest_parser import parse_pytest_output
from harness.feedback.strategy import strategy_hint
from harness.feedback.stuck import StuckDetector, signature_of
from harness.feedback.types import FailureCategory, FailureReport

# Targets simple `assert a == b` (the harness's TDD red-green targets); does not
# parse chained/composite asserts — those degrade gracefully to None captures,
# and strategy_hint already tolerates missing expected/actual.
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
            return FailureReport(is_green=False, category=FailureCategory.TIMEOUT,
                                 failing=["<timeout>"], hint=hint,
                                 traceback_excerpt=stderr[-self.hint_history_lines*80:],
                                 expected=None, actual=None, signature=sig, stuck=False)
        run = parse_pytest_output(tool_result.exit_code, getattr(tool_result, "stdout", ""),
                                  stderr, getattr(tool_result, "junit_xml", ""))
        cat = classify_run(run)
        if cat is None:
            return FailureReport(is_green=True, category=None, failing=[], hint="",
                                 traceback_excerpt="", expected=None, actual=None,
                                 signature="", stuck=False)
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
        return FailureReport(is_green=False, category=cat, failing=failing, hint=hint,
                             traceback_excerpt=excerpt, expected=expected, actual=actual,
                             signature=sig, stuck=stuck)
