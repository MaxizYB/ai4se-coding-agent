from harness.feedback.classifier import classify_failure, classify_run
from harness.feedback.types import FailureCategory, TestFailure, TestRunResult


def _f(exc): return TestFailure("n.test", exc, "m")

def test_env_classes():
    assert classify_failure(_f("ModuleNotFoundError")) is FailureCategory.ENV
    assert classify_failure(_f("ImportError")) is FailureCategory.ENV
    # F7: CollectionError removed — pytest collection errors surface as their
    # underlying exception type; there is no builtin CollectionError.
    assert classify_failure(_f("SyntaxError")) is FailureCategory.ENV

def test_qualified_exception_names_stripped():  # F6: bare-name match
    assert classify_failure(_f("subprocess.TimeoutExpired")) is FailureCategory.TIMEOUT
    assert classify_failure(_f("builtins.ValueError")) is FailureCategory.LOGIC
    assert classify_failure(_f("json.decoder.JSONDecodeError")) is FailureCategory.UNKNOWN

def test_logic_classes():
    assert classify_failure(_f("AssertionError")) is FailureCategory.LOGIC
    assert classify_failure(_f("AttributeError")) is FailureCategory.LOGIC
    assert classify_failure(_f("NameError")) is FailureCategory.LOGIC
    assert classify_failure(_f("TypeError")) is FailureCategory.LOGIC
    assert classify_failure(_f("ValueError")) is FailureCategory.LOGIC

def test_unknown_and_timeout():
    assert classify_failure(_f("RuntimeError")) is FailureCategory.UNKNOWN
    assert classify_failure(TestFailure("n.test", "TimeoutExpired", "m")) is FailureCategory.TIMEOUT

def test_classify_run_green_is_none():
    green = TestRunResult(1, 1, 0, 0, [])
    assert classify_run(green) is None

def test_classify_run_uses_first_failure():
    red = TestRunResult(1, 0, 1, 0, [_f("AssertionError")])
    assert classify_run(red) is FailureCategory.LOGIC
