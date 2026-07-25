from harness.context.manager import Message
from harness.llm.mock import MockLLMClient


def test_script_sequence():
    c = MockLLMClient(["a", "b", "c"])
    assert c.complete([Message("user", "x")]) == "a"
    assert c.complete([Message("user", "x")]) == "b"
    assert c.complete([Message("user", "x")]) == "c"

def test_callable_script():
    c = MockLLMClient(lambda msgs: "ACTION: finish\nREASON: ok\n")
    assert "finish" in c.complete([Message("user", "x")])
