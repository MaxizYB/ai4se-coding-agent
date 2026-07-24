import hashlib

from harness.feedback.types import FailureCategory


def signature_of(failing: list[str], category: FailureCategory) -> str:
    raw = f"{category.value}|{','.join(sorted(failing))}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]

class StuckDetector:
    def __init__(self, repeat_n: int, no_progress_m: int):
        self.repeat_n = repeat_n
        self.no_progress_m = no_progress_m
        self._last_sig = None
        self._repeat = 0
        self._max_failing = 0
        self._no_progress = 0

    def update(self, signature: str, failing: list[str]) -> bool:
        n = len(failing)
        if self._last_sig == signature:
            self._repeat += 1
        else:
            self._repeat = 1
            self._last_sig = signature
        if n < self._max_failing:
            self._no_progress = 0
            self._max_failing = n
        elif n > 0:
            self._no_progress += 1
            self._max_failing = max(self._max_failing, n)
        return self._repeat >= self.repeat_n or self._no_progress >= self.no_progress_m

    def reset(self) -> None:
        self._last_sig = None
        self._repeat = 0
        self._max_failing = 0
        self._no_progress = 0
