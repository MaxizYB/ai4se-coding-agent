from dataclasses import dataclass, field
from enum import Enum

class FailureCategory(str, Enum):
    ENV = "ENV"
    LOGIC = "LOGIC"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"

@dataclass
class TestFailure:
    __test__ = False  # silence pytest collection warning (F9)
    nodeid: str
    exc_type: str
    message: str
    traceback: str = ""

@dataclass
class TestRunResult:
    __test__ = False  # silence pytest collection warning (F9)
    total: int
    passed: int
    failed: int
    errors: int
    failures: list[TestFailure] = field(default_factory=list)
    exit_code: int = 0  # F3: is_green must include exit_code==0 (SPEC §3.6)

    @property
    def is_green(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.exit_code == 0

@dataclass
class FailureReport:
    is_green: bool
    category: "FailureCategory | None"
    failing: list[str]
    hint: str
    traceback_excerpt: str
    expected: "str | None"
    actual: "str | None"
    signature: str
    stuck: bool
