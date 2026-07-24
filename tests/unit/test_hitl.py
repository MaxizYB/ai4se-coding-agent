from harness.actions.protocol import RunShell
from harness.guardrails.guardrail import Allow, Deny
from harness.guardrails.hitl import HITL, FailClosedApprover, StubApprover


def test_approved_returns_allow():
    h = HITL(StubApprover(approve=True))
    assert isinstance(h.request(RunShell("rm -rf build"), "danger"), Allow)

def test_denied_returns_deny():
    h = HITL(StubApprover(approve=False))
    assert isinstance(h.request(RunShell("rm -rf build"), "danger"), Deny)

def test_fail_closed_always_denies():
    assert FailClosedApprover().ask(RunShell("x"), "r") is False
