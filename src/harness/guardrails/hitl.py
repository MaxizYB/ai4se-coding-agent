from typing import Protocol

from harness.actions.protocol import Action
from harness.guardrails.guardrail import Allow, Deny, GuardrailDecision


class Approver(Protocol):
    def ask(self, action: Action, reason: str) -> bool: ...

class StubApprover:
    def __init__(self, approve: bool): self.approve = approve
    def ask(self, action: Action, reason: str) -> bool: return self.approve

class FailClosedApprover:
    def ask(self, action: Action, reason: str) -> bool: return False

class ConsoleApprover:
    def ask(self, action: Action, reason: str) -> bool:
        ans = input(f"APPROVE? {reason} [{type(action).__name__}] [y/N]: ")
        return ans.strip().lower() == "y"

class HITL:
    def __init__(self, approver: Approver):
        self.approver = approver

    def request(self, action: Action, reason: str) -> GuardrailDecision:
        if self.approver.ask(action, reason):
            return Allow()
        return Deny(f"human denied: {reason}")
