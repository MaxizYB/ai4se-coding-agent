class MockLLMClient:
    def __init__(self, script):
        self.script = script
        self._i = 0

    def complete(self, messages) -> str:
        if callable(self.script):
            return self.script(messages)
        out = self.script[self._i % len(self.script)]
        self._i += 1
        return out
