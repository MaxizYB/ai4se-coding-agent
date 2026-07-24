from harness.feedback.strategy import strategy_hint
from harness.feedback.types import FailureCategory


def test_env_hint_mentions_deps_not_logic():
    h = strategy_hint(FailureCategory.ENV, exc="ModuleNotFoundError")
    assert "依赖" in h or "import" in h.lower()
    assert "不要改断言" in h

def test_logic_hint_carries_expected_actual():
    h = strategy_hint(FailureCategory.LOGIC, nodeid="t.test_add", expected="4", actual="3")
    assert "test_add" in h and "4" in h and "3" in h

def test_timeout_hint_mentions_budget():
    h = strategy_hint(FailureCategory.TIMEOUT, budget_s=30)
    assert "30" in h and ("死循环" in h or "超时" in h)

def test_unknown_hint_mentions_diagnose():
    assert "诊断" in strategy_hint(FailureCategory.UNKNOWN)

def test_green_is_empty():
    assert strategy_hint(None) == ""
