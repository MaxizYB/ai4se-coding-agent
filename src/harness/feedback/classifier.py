from harness.feedback.types import FailureCategory, TestFailure, TestRunResult

_ENV = {"ModuleNotFoundError", "ImportError", "SyntaxError"}     # F7: dropped phantom CollectionError
_LOGIC = {"AssertionError", "AttributeError", "NameError", "TypeError", "ValueError"}

def classify_failure(failure: TestFailure) -> FailureCategory:
    # F6: strip module prefix so qualified names (subprocess.TimeoutExpired,
    # builtins.ValueError, json.decoder.JSONDecodeError) classify correctly.
    exc = failure.exc_type.rsplit('.', 1)[-1]
    if exc == "TimeoutExpired":
        return FailureCategory.TIMEOUT
    if exc in _ENV:
        return FailureCategory.ENV
    if exc in _LOGIC:
        return FailureCategory.LOGIC
    return FailureCategory.UNKNOWN

def classify_run(result: TestRunResult) -> FailureCategory | None:
    if result.is_green or not result.failures:
        return None
    return classify_failure(result.failures[0])
