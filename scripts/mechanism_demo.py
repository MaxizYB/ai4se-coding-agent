"""§A.6 deterministic mechanism demo. Runs fully offline with a mock LLM."""
import os
import sys

# Bootstrap: put the in-tree `src/` on sys.path so `python scripts/mechanism_demo.py`
# works standalone (PEP 668 forbids `pip install -e .` on this externally-managed
# interpreter; pyproject's `pythonpath=["src"]` only covers pytest, not subprocess).
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.realpath(os.path.join(_HERE, os.pardir, "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from harness.actions.protocol import RunShell
from harness.config import Config
from harness.feedback.engine import FeedbackEngine
from harness.feedback.types import FailureCategory
from harness.guardrails.guardrail import AskHuman, Guardrail

GREEN_XML = '<?xml version="1.0"?><testsuite tests="1" failures="0" errors="0"><testcase name="t" classname="x"/></testsuite>'
ASSERT_XML = '<?xml version="1.0"?><testsuite tests="1" failures="1" errors="0"><testcase name="t" classname="x"><failure type="AssertionError" message="assert 3 == 4">assert 3 == 4</failure></testcase></testsuite>'
IMPORT_XML = '<?xml version="1.0"?><testsuite tests="0" failures="0" errors="1"><testcase name="c" classname="x"><error type="ModuleNotFoundError" message="No module named \'foo\'">x</error></testcase></testsuite>'


class TR:
    def __init__(self, exit_code, xml, stderr=""):
        self.exit_code = exit_code
        self.junit_xml = xml
        self.stderr = stderr
        self.stdout = ""


def demo1_guardrail():
    cfg = Config.default()
    cfg.dangerous_shell_patterns = [r"rm\s+-rf?"]
    g = Guardrail(cfg)
    d = g.check(RunShell("rm -rf /"))
    print("① guardrail intercept:", type(d).__name__, "-", getattr(d, "reason", ""))
    assert isinstance(d, AskHuman)


def demo2_feedback_changes_action():
    eng = FeedbackEngine(30, 99, 99, 8)
    fb = eng.classify(TR(1, ASSERT_XML))
    print("② feedback hint (drives next edit):", fb.hint.strip())
    # "修实现逻辑" uniquely identifies the LOGIC branch; "断言" alone is
    # non-discriminating because the ENV hint also contains it ("不要改断言逻辑").
    assert "修实现逻辑" in fb.hint


def demo3_categories_differ():
    eng = FeedbackEngine(30, 99, 99, 8)
    logic = eng.classify(TR(1, ASSERT_XML))
    env = eng.classify(TR(2, IMPORT_XML))
    timeout = eng.classify(TR(124, "", stderr="subprocess.TimeoutExpired: 30"))
    print("③ LOGIC:", logic.category.value, "| ENV:", env.category.value, "| TIMEOUT:", timeout.category.value)
    assert {logic.category, env.category, timeout.category} == {
        FailureCategory.LOGIC,
        FailureCategory.ENV,
        FailureCategory.TIMEOUT,
    }
    # Lock hint-distinctness: a strategy_hint regression collapsing every category
    # to one template (but keeping the right category labels) must fail here.
    assert len({logic.hint, env.hint, timeout.hint}) == 3


def main():
    print("=== §A.6 Mechanism Demo (offline, mock LLM) ===")
    demo1_guardrail()
    demo2_feedback_changes_action()
    demo3_categories_differ()
    print("=== all mechanism assertions passed ===")


if __name__ == "__main__":
    main()
