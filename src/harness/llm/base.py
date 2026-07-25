from typing import Protocol

from harness.context.manager import Message


class LLMClient(Protocol):
    def complete(self, messages: list[Message]) -> str: ...
