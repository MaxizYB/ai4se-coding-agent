# Coding Agent Harness Implementation Plan

> **Task Status Summary** (§4.7: 每完成一个 task 即标记完成并附 commit hash)

| Task | Module | Status | Commit |
|------|--------|--------|--------|
| T0 | Project bootstrap | ✅ done | `e12d37c` |
| T1 | Action protocol (types) | ✅ done | `8c9897c` |
| T2 | Action parser (text→Action) | ✅ done | `fa2727a`+`3cf1940` |
| T3 | Feedback types + junit parser | ✅ done | `67ada5a` |
| T4 | Failure classifier | ✅ done | `8c778a1` |
| T5 | Strategy map | ✅ done | `d1e0a1b` |
| T6 | Stuck detector | ✅ done | `33f6d7f` |
| T7 | FeedbackEngine | ✅ done | `ab8711d`+`c70740c`..`1ccc551` |
| T8 | Config | ✅ done | `f160521` |
| T9 | Guardrail | ✅ done | `f7f4f01` |
| T10 | HITL | ✅ done | `15743ee` |
| T11 | CredentialStore | ✅ done | `41bad7c`+`54ce698` |
| T12 | MemoryStore | ✅ done | `d4d9b13` |
| T13 | Test runner | ✅ done | `df2afc9` |
| T14 | ToolDispatcher | ✅ done | `cc1f7f9` |
| T15 | ContextManager | ✅ done | `19935e5` |
| T16 | LLMClient + Mock | ✅ done | `a81bb38` |
| T17 | AgentRunner (★) | ✅ done | `fa39670`+`5f94c12`+`186e786`..`213d7f7` |
| T18 | ZhipuLLMClient | ✅ done | `6a0f6bc` |
| T19 | CLI | ✅ done | `13db363`+`5c6bc68` |
| T20 | §A.6 mechanism demo | ✅ done | `d68552d`+`85a81e9` |
| T21 | WebUI | ✅ done | `d6301cc`+`5de9c02`+`ce9f5af`+`8964e2f`+`7665da7`+`573c4a3`+`d477672`+`ce6d5d6`+`783b557`+`45dbb5a` |
| T22 | Docker + CI | ✅ done | `7828fc5`+`5de9c02` |
| Chat-T1..T6 | Conversational CLI (split_prose/presenter/build_chat/ChatRunner/cli/docs) | ✅ done | `7b0aed2`..`b3cfd32` |
| Gov-G1..G5 | Governance deep-dim (Sandbox/Diff/TaskReport/Docker) | ✅ done | `bed37f3`..`e03b134` |
| Mem-M1..M4 | Memory deep-dim (Compactor/AGENTS.md/@mention/Retriever) | ✅ done | `18b9a7b`..`ab11b3c` |

> Branches used as PR-equivalents (local ff-merge per `finishing-a-development-branch` skill):
> `feat/feedback-core`, `feat/governance`, `feat/pr3`, `feat/pr4`, `feat/pr5`, `feat/chat`, `feat/governance-deep-dim`, `feat/memory-context-deep-dim`.
> Subagent identity + human interventions documented in `AGENT_LOG.md`.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-coded Python Coding Agent Harness that autonomously fixes a failing pytest test (TDD red→green) via a deterministic feedback loop, with governance, credentials, mock-LLM unit tests, a thin WebUI, and Docker/PyPI distribution.

**Architecture:** `AgentRunner` main loop drives a mockable `LLMClient` (raw text only); `ActionParser` turns text into typed `Action`s; `Guardrail`+`HITL` gate execution; `ToolDispatcher` executes; `FeedbackEngine` (★ deep dimension) parses junit XML into a failure taxonomy, maps to a strategy hint, detects stuck, and feeds a `FailureReport` back via `ContextManager`. LLM only ever decides "next step" — all structure is our code (§A.4-A).

**Tech Stack:** Python 3.11+, pytest, `cryptography` (Fernet/PBKDF2), FastAPI/uvicorn (WebUI), stdlib `subprocess`/`xml.etree`/`tomllib`. Real LLM: 智谱 GLM.

## Global Constraints

- Python ≥ 3.11 (uses `tomllib`).
- TDD hard requirement (通用 §3.6): every task writes the failing test first, runs it red, implements minimal code, runs green, commits. No implementation before its test.
- §A.4-A/C: the harness kernel must be self-coded; every core mechanism must be deterministic-unit-testable with a mock/stub LLM (no network in default tests).
- §3.1: API key never hardcoded / committed / logged; `.env`/`*.key`/`credentials.enc` git-ignored (already in `.gitignore`).
- Credential threat model (§12): Fernet + PBKDF2 ≥200k iters; master password unrecoverable.
- Scope fence default: `allowed_write_dirs = ["src"]`; test directory read-only (SPEC §10-U1) so the agent cannot "cheat" by editing tests.
- Run-tests backbone: `pytest --junitxml=<tmp> --tb=short` (stable structured output), NOT text scraping.
- One action per LLM turn; protocol is provider-agnostic structured text (no tool-calling API).
- CI (§五.6): `.gitlab-ci.yml` with a job named `unit-test`; container distribution ⇒ CI also builds image.
- Naming/copy: CLI binary is `harness`; console commands `init` / `key` / `fix`.

---

## File Structure

```
pyproject.toml                  # package + console script `harness` + pytest/deps
Makefile                        # `make test`, `make lint`, `make demo`
harness.toml.example            # documented default config
Dockerfile                      # python-slim + harness
.gitlab-ci.yml                  # unit-test job + image build
src/harness/__init__.py
src/harness/config.py           # Config dataclass + load_config (harness.toml)
src/harness/credentials.py      # CredentialStore (Fernet + PBKDF2)
src/harness/actions/__init__.py
src/harness/actions/protocol.py # Action dataclasses (tagged union)
src/harness/actions/parser.py   # parse_action(text)->Action, ParseError
src/harness/tools/__init__.py
src/harness/tools/runner.py     # run_tests subprocess + junit + timeout
src/harness/tools/dispatcher.py # ToolDispatcher + ToolResult
src/harness/guardrails/__init__.py
src/harness/guardrails/guardrail.py  # Guardrail.check + GuardrailDecision
src/harness/guardrails/hitl.py       # HITL + Approver protocol + impls
src/harness/feedback/__init__.py
src/harness/feedback/types.py   # FailureCategory, TestFailure, TestRunResult, FailureReport
src/harness/feedback/pytest_parser.py  # parse_pytest_output -> TestRunResult
src/harness/feedback/classifier.py     # classify_failure / classify_run
src/harness/feedback/strategy.py       # strategy_hint
src/harness/feedback/stuck.py          # StuckDetector
src/harness/feedback/engine.py         # FeedbackEngine.classify -> FailureReport
src/harness/context/__init__.py
src/harness/context/manager.py  # ContextManager + Message + locate_impl_module
src/harness/memory/__init__.py
src/harness/memory/store.py     # MemoryStore (notes + JSONL run log)
src/harness/llm/__init__.py
src/harness/llm/base.py         # LLMClient Protocol
src/harness/llm/mock.py         # MockLLMClient
src/harness/llm/zhipu.py        # ZhipuLLMClient (real, gated live test)
src/harness/agent.py            # AgentRunner main loop + Task/Turn/RunResult
src/harness/cli.py              # `harness init|key|fix`
web/app.py                      # FastAPI thin WebUI + SSE stream
web/templates/index.html
scripts/mechanism_demo.py       # §A.6 deterministic mechanism demo
tests/unit/...                  # pure-function tests (no network)
tests/integration/...           # mock-LLM AgentRunner tests
tests/fixtures/                 # canned junit XML, tiny repo fixtures
```

## Dependency & Parallelism Map

- **Layer 0 (bootstrap):** T0.
- **Layer 1 (pure leaves, parallelizable):** T1 (actions/protocol), T3 (feedback/types), T8 (config), T11 (credentials), T12 (memory) — no internal deps.
- **Layer 2 (depend on L1):** T2 (parser←T1), T4 (classifier←T3), T5 (strategy←T4), T6 (stuck←T3), T9 (guardrail←T1,T8), T10 (hitl).
- **Layer 3:** T7 (engine←T3,T4,T5,T6,T8), T13 (runner), T14 (dispatcher←T1,T13,T9), T16 (llm base+mock←context Message).
- **Layer 4:** T15 (context manager←T7,T12), T17 (agent←all).
- **Layer 5:** T18 (zhipu←T11), T19 (cli←T17), T20 (demo←T17), T21 (web←T17), T22 (docker/ci).
- **Parallel worktree groups:** {T1,T3,T8,T11,T12} together; {T4,T5,T6} together; {T9,T10,T13} together. Each task ends independently testable.

---

## Task 0: Project Bootstrap

**Files:**
- Create: `pyproject.toml`, `Makefile`, `harness.toml.example`, `src/harness/__init__.py` (empty), `tests/__init__.py` (empty), `tests/unit/__init__.py` (empty)

**Interfaces:**
- Produces: `make test` entrypoint; importable `harness` package; pytest configured.

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "harness"
version = "0.1.0"
requires-python = ">=3.11"
# F8: core harness kernel is stdlib-only; heavy deps are optional so the
# feedback/guardrail/parsing tasks (T1-T10) stay hermetic without network.
dependencies = []

[project.optional-dependencies]
full = ["cryptography>=42", "fastapi>=0.110", "uvicorn>=0.29", "httpx>=0.27"]
dev = ["pytest>=8", "ruff"]

[project.scripts]
harness = "harness.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q"
markers = ["live: tests calling a real LLM (deselect with -m 'not live')"]
```

- [ ] **Step 2: Write Makefile**

```makefile
.PHONY: test lint demo
test:
	pytest -m "not live"
lint:
	ruff check src tests
demo:
	python scripts/mechanism_demo.py
```

- [ ] **Step 3: Write harness.toml.example**

```toml
[scope]
project_root = "."
allowed_write_dirs = ["src"]

[guardrails]
dangerous_shell_patterns = ["rm\\s+-rf?", "git\\s+push\\s+(-f|--force)", "DROP\\s+TABLE", ":\\(\\)\\s*\\{"]
network_commands = ["pip install", "npm install", "curl", "wget"]
fail_closed_when_noninteractive = true

[budget]
max_iterations = 20
max_parse_failures = 5
stuck_repeat_n = 3
stuck_no_progress_m = 4
test_timeout_s = 30

[feedback]
hint_history_lines = 8
```

- [ ] **Step 4: Create empty packages + verify pytest collects nothing cleanly**

Run: `mkdir -p src/harness tests/unit && touch src/harness/__init__.py tests/__init__.py tests/unit/__init__.py && pip install -e ".[dev]" && pytest -m "not live"`
Expected: pytest exits 5 (no tests collected) or 0 — the gate is **no collection errors**. (F4: modern pytest returns exit 5 on an empty suite, not 0.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Makefile harness.toml.example src/harness/__init__.py tests/__init__.py tests/unit/__init__.py
git commit -m "chore: project bootstrap (pyproject, make test, config example)"
```

---

## Task 1: Action Protocol (typed actions)

**Files:**
- Create: `src/harness/actions/__init__.py` (empty), `src/harness/actions/protocol.py`
- Test: `tests/unit/test_actions_protocol.py`

**Interfaces:**
- Produces: `Action` base + `ReadFile`, `ListDir`, `WriteFile`, `EditFile`, `RunShell`, `RunTests`, `Finish` (all `@dataclass(frozen=True)` subclassing `Action`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_actions_protocol.py
from harness.actions.protocol import (
    Action, ReadFile, ListDir, WriteFile, EditFile, RunShell, RunTests, Finish,
)

def test_actions_are_frozen_and_tagged():
    assert isinstance(ReadFile("a.py"), Action)
    assert isinstance(RunTests("tests/test_x.py::test_t"), Action)
    assert isinstance(Finish("done"), Action)

def test_equality_and_fields():
    assert EditFile("a.py", "old", "new") == EditFile("a.py", "old", "new")
    assert WriteFile("a.py", "x").content == "x"
    assert RunShell("ls").command == "ls"
    assert ListDir(".").path == "."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_actions_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.actions.protocol`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/actions/protocol.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Action:
    pass

@dataclass(frozen=True)
class ReadFile(Action):
    path: str

@dataclass(frozen=True)
class ListDir(Action):
    path: str

@dataclass(frozen=True)
class WriteFile(Action):
    path: str
    content: str

@dataclass(frozen=True)
class EditFile(Action):
    path: str
    old: str
    new: str

@dataclass(frozen=True)
class RunShell(Action):
    command: str

@dataclass(frozen=True)
class RunTests(Action):
    args: str = ""

@dataclass(frozen=True)
class Finish(Action):
    reason: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_actions_protocol.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/actions tests/unit/test_actions_protocol.py
git commit -m "feat(actions): typed Action protocol (tagged union)"
```

---

## Task 2: Action Parser (text protocol → Action)

**Files:**
- Create: `src/harness/actions/parser.py`
- Test: `tests/unit/test_actions_parser.py`

**Interfaces:**
- Consumes: `Action` types, `ReadFile/WriteFile/EditFile/RunShell/RunTests/Finish` from Task 1.
- Produces: `ParseError(Exception)` with `.reason`; `parse_action(text: str) -> Action`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_actions_parser.py
import pytest
from harness.actions.parser import parse_action, ParseError
from harness.actions.protocol import ReadFile, WriteFile, EditFile, RunTests, RunShell, Finish

def test_parse_simple_param_action():
    a = parse_action("sure, here:\nACTION: read_file\nPATH: src/foo.py\n")
    assert a == ReadFile("src/foo.py")

def test_parse_write_file_with_content_block():
    raw = "ACTION: write_file\nPATH: a.py\n<<<\ndef f():\n    return 1\n>>>\n"
    assert parse_action(raw) == WriteFile("a.py", "def f():\n    return 1\n")

def test_parse_edit_file_old_new_blocks():
    raw = ("ACTION: edit_file\nPATH: a.py\n<<<OLD\n    return 1\n>>>OLD\n"
           "<<<NEW\n    return 2\n>>>NEW\n")
    assert parse_action(raw) == EditFile("a.py", "    return 1\n", "    return 2\n")

def test_parse_run_tests_and_shell_and_finish():
    assert parse_action("ACTION: run_tests\nARGS: t.py::test_a\n") == RunTests("t.py::test_a")
    assert parse_action("ACTION: run_tests\n") == RunTests("")
    assert parse_action("ACTION: run_shell\nCOMMAND: pip list\n") == RunShell("pip list")
    assert parse_action("ACTION: finish\nREASON: green\n") == Finish("green")

def test_tolerates_surrounding_prose():
    a = parse_action("Let me read it.\nACTION: read_file\nPATH: x.py\nNow I'll act.")
    assert a == ReadFile("x.py")

def test_parse_error_on_missing_action():
    with pytest.raises(ParseError):
        parse_action("no action here at all")

def test_parse_error_on_unterminated_block():
    with pytest.raises(ParseError):
        parse_action("ACTION: write_file\nPATH: a.py\n<<<\nnever closed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_actions_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/actions/parser.py
import re
from harness.actions.protocol import (
    Action, ReadFile, ListDir, WriteFile, EditFile, RunShell, RunTests, Finish,
)

class ParseError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason

_BLOCK = re.compile(r"<<<(?P<tag>[A-Z]*)\n(?P<body>.*?)>>> (?P=tag)\n", re.S)
_ACTION_RE = re.compile(r"ACTION:\s*(?P<name>\w+)\b")

_SIMPLE = {
    "read_file": lambda p: ReadFile(p["PATH"]),
    "list_dir": lambda p: ListDir(p["PATH"]),
    "run_shell": lambda p: RunShell(p["COMMAND"]),
    "run_tests": lambda p: RunTests(p.get("ARGS", "")),
    "finish": lambda p: Finish(p.get("REASON", "")),
}

def _parse_params(block: str) -> dict:
    params = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith("<<<"):
            k, _, v = line.partition(":")
            params[k.strip()] = v.strip()
    return params

def parse_action(text: str) -> Action:
    m = _ACTION_RE.search(text)
    if not m:
        raise ParseError("no ACTION: line found")
    name = m.group("name")
    tail = text[m.end():]
    params = _parse_params(tail)
    blocks = {b.group("tag") or "DEFAULT": b.group("body")
              for b in _BLOCK.finditer(tail)}
    if name == "write_file":
        body = blocks.get("DEFAULT")
        if body is None:
            raise ParseError("write_file requires a content block")
        return WriteFile(params["PATH"], body)
    if name == "edit_file":
        old = blocks.get("OLD"); new = blocks.get("NEW")
        if old is None or new is None:
            raise ParseError("edit_file requires <<<OLD and <<<NEW blocks")
        return EditFile(params["PATH"], old, new)
    builder = _SIMPLE.get(name)
    if builder is None:
        raise ParseError(f"unknown action: {name}")
    try:
        return builder(params)
    except KeyError as e:
        raise ParseError(f"missing parameter {e} for {name}") from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_actions_parser.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/actions/parser.py tests/unit/test_actions_parser.py
git commit -m "feat(actions): deterministic text-protocol parser + ParseError"
```

---

## Task 3: Feedback Types + pytest junit Parser

**Files:**
- Create: `src/harness/feedback/__init__.py` (empty), `src/harness/feedback/types.py`, `src/harness/feedback/pytest_parser.py`
- Test: `tests/unit/test_pytest_parser.py`, `tests/fixtures/green.xml`, `tests/fixtures/assertion.xml`, `tests/fixtures/import_err.xml`

**Interfaces:**
- Produces:
  - `FailureCategory(str, Enum)`: `ENV`, `LOGIC`, `TIMEOUT`, `UNKNOWN`.
  - `@dataclass TestFailure{nodeid:str; exc_type:str; message:str; traceback:str}`.
  - `@dataclass TestRunResult{total:int; passed:int; failed:int; errors:int; failures:list[TestFailure]}` with property `is_green`.
  - `@dataclass FailureReport{is_green:bool; category:FailureCategory|None; failing:list[str]; hint:str; traceback_excerpt:str; expected:str|None; actual:str|None; signature:str; stuck:bool}` (consumed by Tasks 7, 15, 17).
  - `parse_pytest_output(exit_code:int, stdout:str, stderr:str, junit_xml:str) -> TestRunResult`.

- [ ] **Step 1: Write fixtures**

```xml
<!-- tests/fixtures/green.xml -->
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="t" tests="2" failures="0" errors="0">
  <testcase name="test_a" classname="t"/>
  <testcase name="test_b" classname="t"/>
</testsuite>
```

```xml
<!-- tests/fixtures/assertion.xml -->
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="t" tests="1" failures="1" errors="0">
  <testcase name="test_add" classname="t.Tests">
    <failure type="AssertionError" message="assert 3 == 4">assert 3 == 4</failure>
  </testcase>
</testsuite>
```

```xml
<!-- tests/fixtures/import_err.xml -->
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="t" tests="0" failures="0" errors="1">
  <testcase name="collection" classname="t">
    <error type="ModuleNotFoundError" message="No module named 'foo'">ModuleNotFoundError: No module named 'foo'</error>
  </testcase>
</testsuite>
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_pytest_parser.py
from pathlib import Path
from harness.feedback.pytest_parser import parse_pytest_output
from harness.feedback.types import FailureCategory

FIX = Path(__file__).parent.parent / "fixtures"

def _xml(name): return (FIX / name).read_text()

def test_green_run():
    r = parse_pytest_output(0, "", "", _xml("green.xml"))
    assert r.is_green and r.failed == 0 and r.errors == 0 and r.passed == 2

def test_assertion_failure_parsed():
    r = parse_pytest_output(1, "", "", _xml("assertion.xml"))
    assert not r.is_green and r.failed == 1
    f = r.failures[0]
    assert f.nodeid == "t.Tests.test_add"
    assert f.exc_type == "AssertionError"

def test_import_error_from_collection():
    r = parse_pytest_output(2, "", "", _xml("import_err.xml"))
    assert not r.is_green and r.errors == 1
    assert r.failures[0].exc_type == "ModuleNotFoundError"

def test_no_xml_falls_back_to_stderr():
    r = parse_pytest_output(2, "", "ModuleNotFoundError: No module named 'foo'", "")
    assert not r.is_green and r.failures[0].exc_type == "ModuleNotFoundError"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_pytest_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.feedback.pytest_parser`.

- [ ] **Step 4: Write minimal implementation**

```python
# src/harness/feedback/types.py
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
```

```python
# src/harness/feedback/pytest_parser.py
import re
import xml.etree.ElementTree as ET
from harness.feedback.types import TestFailure, TestRunResult

# F2: include `Expired` so subprocess.TimeoutExpired in stderr reaches TIMEOUT.
_EXC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Expired)):")

def _nodeid(clsname: str, name: str) -> str:
    # NOTE (F1): junit gives classname (dotted module) + name, NOT pytest's
    # `path::name` selector. We emit `classname.name` as the display nodeid;
    # correlation to Task.test_selector is by TEST-NAME suffix (see Task 7
    # `test_name_of`), since the red-green fixer normally targets one test.
    return f"{clsname}.{name}" if clsname else name

def parse_pytest_output(exit_code: int, stdout: str, stderr: str, junit_xml: str) -> TestRunResult:
    if not junit_xml.strip():
        # F5: use the LAST regex match in stderr (the actually-raised exception),
        # not the first, so chained exceptions classify the raised frame.
        matches = _EXC_RE.findall(stderr)
        exc = matches[-1] if matches else "UnknownError"
        msg = stderr.strip().splitlines()[-1] if stderr.strip() else ""
        return TestRunResult(0, 0, 0, 1, [TestFailure("<collection>", exc, msg)], exit_code)
    root = ET.fromstring(junit_xml)
    total = int(root.get("tests", 0)); failed = int(root.get("failures", 0))
    errors = int(root.get("errors", 0)); passed = total - failed - errors
    failures = []
    for tc in root.findall("testcase"):
        nodeid = _nodeid(tc.get("classname", ""), tc.get("name", ""))
        for tag in ("failure", "error"):
            el = tc.find(tag)
            if el is not None:
                failures.append(TestFailure(nodeid, el.get("type", "UnknownError"),
                                            el.get("message", ""), el.text or ""))
    return TestRunResult(total, max(passed, 0), failed, errors, failures, exit_code)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_pytest_parser.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/harness/feedback tests/unit/test_pytest_parser.py tests/fixtures
git commit -m "feat(feedback): types + deterministic junit XML parser (stderr fallback)"
```

---

## Task 4: Failure Classifier

**Files:**
- Create: `src/harness/feedback/classifier.py`
- Test: `tests/unit/test_classifier.py`

**Interfaces:**
- Consumes: `TestFailure`, `TestRunResult`, `FailureCategory` from Task 3.
- Produces: `classify_failure(failure: TestFailure) -> FailureCategory`; `classify_run(result: TestRunResult) -> FailureCategory | None` (None when green).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_classifier.py
from harness.feedback.types import TestFailure, TestRunResult, FailureCategory
from harness.feedback.classifier import classify_failure, classify_run

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/feedback/classifier.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_classifier.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/feedback/classifier.py tests/unit/test_classifier.py
git commit -m "feat(feedback): rule-based failure classifier (ENV/LOGIC/TIMEOUT/UNKNOWN)"
```

---

## Task 5: Strategy Map (category → hint)

**Files:**
- Create: `src/harness/feedback/strategy.py`
- Test: `tests/unit/test_strategy.py`

**Interfaces:**
- Consumes: `FailureCategory` from Task 3.
- Produces: `strategy_hint(category: FailureCategory, *, nodeid: str = "", expected: str | None = None, actual: str | None = None, budget_s: float | None = None, exc: str = "") -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_strategy.py
from harness.feedback.types import FailureCategory
from harness.feedback.strategy import strategy_hint

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/feedback/strategy.py
from harness.feedback.types import FailureCategory

def strategy_hint(category, *, nodeid="", expected=None, actual=None,
                  budget_s=None, exc="") -> str:
    if category is None:
        return ""
    if category is FailureCategory.ENV:
        return (f"测试未运行：{exc or '环境错误'}。先查依赖/导入/路径，"
                f"在收集成功前不要改断言逻辑。")
    if category is FailureCategory.LOGIC:
        ea = f"期望 {expected}，实际 {actual}。" if expected or actual else ""
        return f"断言失败@{nodeid}：{ea}修实现逻辑。"
    if category is FailureCategory.TIMEOUT:
        return f"测试超时（{budget_s}s）。疑似死循环或慢路径，重审算法。"
    return "未分类失败，原始 traceback 见下。先诊断再改。"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_strategy.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/feedback/strategy.py tests/unit/test_strategy.py
git commit -m "feat(feedback): deterministic strategy-hint map per failure category"
```

---

## Task 6: Stuck Detector

**Files:**
- Create: `src/harness/feedback/stuck.py`
- Test: `tests/unit/test_stuck.py`

**Interfaces:**
- Produces: `StuckDetector(repeat_n: int, no_progress_m: int)` with `update(signature: str, failing: list[str]) -> bool` (returns True when stuck) and `reset()`. Also module function `signature_of(failing: list[str], category) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_stuck.py
from harness.feedback.stuck import StuckDetector, signature_of
from harness.feedback.types import FailureCategory

def test_signature_stable_ignores_order():
    assert signature_of(["a", "b"], FailureCategory.LOGIC) == \
           signature_of(["b", "a"], FailureCategory.LOGIC)

def test_stuck_on_repeated_signature():
    d = StuckDetector(repeat_n=3, no_progress_m=10)
    sig = signature_of(["t.x"], FailureCategory.LOGIC)
    assert d.update(sig, ["t.x"]) is False
    assert d.update(sig, ["t.x"]) is False
    assert d.update(sig, ["t.x"]) is True   # 3rd consecutive repeat

def test_not_stuck_when_changing():
    d = StuckDetector(repeat_n=3, no_progress_m=10)
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is False
    assert d.update(signature_of(["b"], FailureCategory.LOGIC), ["b"]) is False

def test_no_progress_when_failing_set_never_shrinks():
    d = StuckDetector(repeat_n=99, no_progress_m=3)
    d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"])   # largest so far = 1
    d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"])   # no shrink
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is True  # m=3

def test_progress_resets_stuck():
    d = StuckDetector(repeat_n=2, no_progress_m=2)
    d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"])
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is True
    d.reset()
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_stuck.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/feedback/stuck.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_stuck.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/feedback/stuck.py tests/unit/test_stuck.py
git commit -m "feat(feedback): stuck detector (signature repeat + no-progress)"
```

---

## Task 7: Feedback Engine (orchestrator → FailureReport)

**Files:**
- Create: `src/harness/feedback/engine.py`
- Test: `tests/unit/test_feedback_engine.py`

**Interfaces:**
- Consumes: Tasks 3–6 (`parse_pytest_output`, `classify_run`, `strategy_hint`, `StuckDetector`, `signature_of`, types), `Config` from Task 8 (forward reference — engine takes plain ints here to decouple: see below).
- Produces: `@dataclass FailureReport{is_green:bool; category: FailureCategory|None; failing:list[str]; hint:str; traceback_excerpt:str; expected:str|None; actual:str|None; signature:str; stuck:bool}`; `FeedbackEngine(test_timeout_s:int, stuck_repeat_n:int, stuck_no_progress_m:int, hint_history_lines:int)` with `.classify(tool_result) -> FailureReport`. `tool_result` is any object with `exit_code, stdout, stderr, junit_xml`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_feedback_engine.py
from pathlib import Path
from harness.feedback.engine import FeedbackEngine
from harness.feedback.types import FailureCategory

FIX = Path(__file__).parent.parent / "fixtures"
def _xml(n): return (FIX / n).read_text()

class TR:  # minimal duck-typed tool result
    def __init__(self, exit_code, junit, stderr=""): self.exit_code=exit_code; self.junit_xml=junit; self.stderr=stderr; self.stdout=""

def test_green_report():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(0, _xml("green.xml")))
    assert r.is_green and r.category is None and r.hint == "" and not r.stuck

def test_logic_report_has_hint_and_signature():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(1, _xml("assertion.xml")))
    assert r.category is FailureCategory.LOGIC
    assert "断言" in r.hint and r.signature and r.failing == ["t.Tests.test_add"]

def test_env_report():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(2, _xml("import_err.xml")))
    assert r.category is FailureCategory.ENV and "不要改断言" in r.hint

def test_stuck_flag_after_repeats():
    eng = FeedbackEngine(30, 3, 10, 8)
    reports = [eng.classify(TR(1, _xml("assertion.xml"))) for _ in range(3)]
    assert not reports[0].stuck and not reports[1].stuck and reports[2].stuck is True

def test_timeout_report():
    eng = FeedbackEngine(30, 3, 4, 8)
    r = eng.classify(TR(124, "", stderr="subprocess.TimeoutExpired: 30"))
    assert r.category is FailureCategory.TIMEOUT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_feedback_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/feedback/engine.py
import re
from dataclasses import dataclass
from harness.feedback.types import FailureCategory, FailureReport
from harness.feedback.pytest_parser import parse_pytest_output
from harness.feedback.classifier import classify_run
from harness.feedback.strategy import strategy_hint
from harness.feedback.stuck import StuckDetector, signature_of

_EXPECTED = re.compile(r"assert\s+(?P<a>[^=]+?)\s*==\s*(?P<b>[^\s]+)")

class FeedbackEngine:
    def __init__(self, test_timeout_s: int, stuck_repeat_n: int,
                 stuck_no_progress_m: int, hint_history_lines: int):
        self.test_timeout_s = test_timeout_s
        self.hint_history_lines = hint_history_lines
        self.detector = StuckDetector(stuck_repeat_n, stuck_no_progress_m)

    def classify(self, tool_result) -> FailureReport:
        stderr = getattr(tool_result, "stderr", "")
        if getattr(tool_result, "exit_code", 0) == 124 or "TimeoutExpired" in stderr:
            hint = strategy_hint(FailureCategory.TIMEOUT, budget_s=self.test_timeout_s)
            sig = signature_of(["<timeout>"], FailureCategory.TIMEOUT)
            return FailureReport(False, FailureCategory.TIMEOUT, ["<timeout>"], hint,
                                 stderr[-self.hint_history_lines*80:], None, None, sig, False)
        run = parse_pytest_output(tool_result.exit_code, getattr(tool_result, "stdout", ""),
                                  stderr, getattr(tool_result, "junit_xml", ""))
        cat = classify_run(run)
        if cat is None:
            return FailureReport(True, None, [], "", "", None, None, "", False)
        failing = [f.nodeid for f in run.failures]
        msg = run.failures[0].message if run.failures else ""
        m = _EXPECTED.search(msg)
        expected = m.group("b").strip() if m else None
        actual = m.group("a").strip() if m else None
        hint = strategy_hint(cat, nodeid=failing[0] if failing else "",
                             expected=expected, actual=actual,
                             exc=run.failures[0].exc_type if run.failures else "")
        sig = signature_of(failing, cat)
        stuck = self.detector.update(sig, failing)
        excerpt = "\n".join((run.failures[0].traceback or "").splitlines()[-self.hint_history_lines:])
        return FailureReport(False, cat, failing, hint, excerpt, expected, actual, sig, stuck)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_feedback_engine.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/feedback/engine.py tests/unit/test_feedback_engine.py
git commit -m "feat(feedback): FeedbackEngine -> FailureReport (classify+strategy+stuck)"
```

---

## Task 8: Config

**Files:**
- Create: `src/harness/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `@dataclass Config` with fields: `project_root:str`, `allowed_write_dirs:list[str]`, `dangerous_shell_patterns:list[str]`, `network_commands:list[str]`, `fail_closed_when_noninteractive:bool`, `max_iterations:int`, `max_parse_failures:int`, `stuck_repeat_n:int`, `stuck_no_progress_m:int`, `test_timeout_s:int`, `hint_history_lines:int`, `max_history:int`; `Config.default()` classmethod; `load_config(path: str | None) -> Config` (None ⇒ defaults).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config.py
from harness.config import Config, load_config

def test_defaults_are_safe():
    c = Config.default()
    assert c.allowed_write_dirs == ["src"]
    assert c.fail_closed_when_noninteractive is True
    assert c.max_iterations == 20 and c.test_timeout_s == 30
    assert c.max_history == 8

def test_load_none_returns_defaults():
    assert load_config(None) == Config.default()

def test_load_toml_overrides():
    toml = """
[scope]
allowed_write_dirs = ["src", "lib"]
[budget]
max_iterations = 5
test_timeout_s = 10
"""
    import tempfile, os
    p = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    p.write(toml); p.close()
    c = load_config(p.name); os.unlink(p.name)
    assert c.allowed_write_dirs == ["src", "lib"]
    assert c.max_iterations == 5 and c.test_timeout_s == 10
    assert c.fail_closed_when_noninteractive is True  # untouched keeps default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/config.py
import tomllib
from dataclasses import dataclass, field

@dataclass
class Config:
    project_root: str = "."
    allowed_write_dirs: list[str] = field(default_factory=lambda: ["src"])
    dangerous_shell_patterns: list[str] = field(default_factory=list)
    network_commands: list[str] = field(default_factory=lambda: ["pip install"])
    fail_closed_when_noninteractive: bool = True
    max_iterations: int = 20
    max_parse_failures: int = 5
    stuck_repeat_n: int = 3
    stuck_no_progress_m: int = 4
    test_timeout_s: int = 30
    hint_history_lines: int = 8
    max_history: int = 8

    @classmethod
    def default(cls) -> "Config":
        return cls()

def load_config(path: str | None) -> Config:
    cfg = Config.default()
    if path is None:
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)
    scope = data.get("scope", {}); gr = data.get("guardrails", {}); bud = data.get("budget", {})
    fb = data.get("feedback", {})
    cfg.project_root = scope.get("project_root", cfg.project_root)
    cfg.allowed_write_dirs = scope.get("allowed_write_dirs", cfg.allowed_write_dirs)
    cfg.dangerous_shell_patterns = gr.get("dangerous_shell_patterns", cfg.dangerous_shell_patterns)
    cfg.network_commands = gr.get("network_commands", cfg.network_commands)
    cfg.fail_closed_when_noninteractive = gr.get("fail_closed_when_noninteractive", cfg.fail_closed_when_noninteractive)
    cfg.max_iterations = bud.get("max_iterations", cfg.max_iterations)
    cfg.max_parse_failures = bud.get("max_parse_failures", cfg.max_parse_failures)
    cfg.stuck_repeat_n = bud.get("stuck_repeat_n", cfg.stuck_repeat_n)
    cfg.stuck_no_progress_m = bud.get("stuck_no_progress_m", cfg.stuck_no_progress_m)
    cfg.test_timeout_s = bud.get("test_timeout_s", cfg.test_timeout_s)
    cfg.hint_history_lines = fb.get("hint_history_lines", cfg.hint_history_lines)
    return cfg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/config.py tests/unit/test_config.py
git commit -m "feat(config): Config dataclass + harness.toml loader with safe defaults"
```

---

## Task 9: Guardrail

**Files:**
- Create: `src/harness/guardrails/__init__.py` (empty), `src/harness/guardrails/guardrail.py`
- Test: `tests/unit/test_guardrail.py`

**Interfaces:**
- Consumes: `Action` types (Task 1), `Config` (Task 8).
- Produces: `@dataclass(frozen=True) class GuardrailDecision` base; `Allow`, `Deny(reason:str)`, `AskHuman(reason:str)` subclasses. `Guardrail(config: Config)` with `.check(action: Action) -> GuardrailDecision`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_guardrail.py
from harness.config import Config
from harness.guardrails.guardrail import Guardrail, Allow, Deny, AskHuman
from harness.actions.protocol import ReadFile, WriteFile, RunShell, RunTests

def cfg(patterns=None, net=None, allowed=None):
    c = Config.default()
    c.dangerous_shell_patterns = patterns or [r"rm\s+-rf?"]
    c.network_commands = net or ["pip install", "curl"]
    if allowed: c.allowed_write_dirs = allowed
    return c

def test_read_allowed_in_scope():
    assert isinstance(Guardrail(cfg()).check(ReadFile("src/a.py")), Allow)

def test_write_out_of_scope_denied():
    d = Guardrail(cfg(allowed=["src"])).check(WriteFile("tests/t.py", "x"))
    assert isinstance(d, Deny)

def test_write_in_scope_allowed():
    assert isinstance(Guardrail(cfg(allowed=["src"])).check(WriteFile("src/a.py", "x")), Allow)

def test_dangerous_shell_asks_human():
    assert isinstance(Guardrail(cfg()).check(RunShell("rm -rf build")), AskHuman)

def test_network_command_asks_human():
    assert isinstance(Guardrail(cfg()).check(RunShell("pip install foo")), AskHuman)

def test_safe_shell_allowed():
    assert isinstance(Guardrail(cfg()).check(RunShell("ls")), Allow)

def test_run_tests_allowed():
    assert isinstance(Guardrail(cfg()).check(RunTests("")), Allow)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_guardrail.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/guardrails/guardrail.py
import os
import re
from dataclasses import dataclass
from harness.actions.protocol import Action, ReadFile, ListDir, WriteFile, EditFile, RunShell, RunTests
from harness.config import Config

@dataclass(frozen=True)
class GuardrailDecision: pass
@dataclass(frozen=True)
class Allow(GuardrailDecision): pass
@dataclass(frozen=True)
class Deny(GuardrailDecision): reason: str
@dataclass(frozen=True)
class AskHuman(GuardrailDecision): reason: str

class Guardrail:
    def __init__(self, config: Config):
        self.config = config
        self._danger = [re.compile(p) for p in config.dangerous_shell_patterns]

    def _in_scope(self, path: str) -> bool:
        root = os.path.abspath(self.config.project_root)
        ap = os.path.abspath(os.path.join(root, path))
        if not ap.startswith(root + os.sep) and ap != root:
            return False
        rel = os.path.relpath(ap, root)
        top = rel.split(os.sep)[0]
        return top in self.config.allowed_write_dirs

    def check(self, action: Action) -> GuardrailDecision:
        if isinstance(action, (ReadFile, ListDir)):
            return Allow()
        if isinstance(action, (WriteFile, EditFile)):
            if not self._in_scope(action.path):
                return Deny(f"out-of-scope write: {action.path}")
            return Allow()
        if isinstance(action, RunShell):
            cmd = action.command
            for pat in self._danger:
                if pat.search(cmd):
                    return AskHuman(f"dangerous command: {cmd}")
            for net in self.config.network_commands:
                if cmd.strip().startswith(net) or (" " + net) in cmd:
                    return AskHuman(f"network/system command: {cmd}")
            return Allow()
        if isinstance(action, RunTests):
            return Allow()
        return Allow()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_guardrail.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/guardrails tests/unit/test_guardrail.py
git commit -m "feat(guardrails): scope fence + dangerous/network command guardrail"
```

---

## Task 10: HITL Approval State Machine

**Files:**
- Create: `src/harness/guardrails/hitl.py`
- Test: `tests/unit/test_hitl.py`

**Interfaces:**
- Produces: `Protocol Approver` with `ask(action, reason) -> bool`; `FailClosedApprover`, `StubApprover(approve:bool)`, `ConsoleApprover`; `HITL(approver: Approver)` with `.request(action: Action, reason: str) -> GuardrailDecision` returning `Allow`/`Deny`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_hitl.py
from harness.guardrails.hitl import HITL, StubApprover, FailClosedApprover
from harness.guardrails.guardrail import Allow, Deny
from harness.actions.protocol import RunShell

def test_approved_returns_allow():
    h = HITL(StubApprover(approve=True))
    assert isinstance(h.request(RunShell("rm -rf build"), "danger"), Allow)

def test_denied_returns_deny():
    h = HITL(StubApprover(approve=False))
    assert isinstance(h.request(RunShell("rm -rf build"), "danger"), Deny)

def test_fail_closed_always_denies():
    assert FailClosedApprover().ask(RunShell("x"), "r") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_hitl.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/guardrails/hitl.py
from typing import Protocol
from harness.actions.protocol import Action
from harness.guardrails.guardrail import Allow, Deny, GuardrailDecision

class Approver(Protocol):
    def ask(self, action: Action, reason: str) -> bool: ...

class StubApprover:
    def __init__(self, approve: bool): self.approve = approve
    def ask(self, action, reason): return self.approve

class FailClosedApprover:
    def ask(self, action, reason): return False

class ConsoleApprover:
    def ask(self, action, reason):
        ans = input(f"APPROVE? {reason} [{type(action).__name__}] [y/N]: ")
        return ans.strip().lower() == "y"

class HITL:
    def __init__(self, approver: Approver):
        self.approver = approver

    def request(self, action: Action, reason: str) -> GuardrailDecision:
        if self.approver.ask(action, reason):
            return Allow()
        return Deny(f"human denied: {reason}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_hitl.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/guardrails/hitl.py tests/unit/test_hitl.py
git commit -m "feat(guardrails): HITL approval state machine + Approver strategies"
```

---

## Task 11: Credential Store (Fernet + PBKDF2)

**Files:**
- Create: `src/harness/credentials.py`
- Test: `tests/unit/test_credentials.py`

**Interfaces:**
- Produces: `CredentialStore(path: str)` with `.set(provider:str, key:str, master:str)`, `.get(provider:str, master:str) -> str`, `.status() -> dict[str,bool]`, `.clear()`. Raises `CredentialError(Exception)` on wrong master / missing provider / corrupt.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_credentials.py
import pytest
from harness.credentials import CredentialStore, CredentialError

def test_roundtrip(tmp_path):
    s = CredentialStore(str(tmp_path / "c.enc"))
    s.set("zhipu", "sk-secret", master="pw123")
    assert s.get("zhipu", "pw123") == "sk-secret"

def test_status_no_plaintext(tmp_path):
    p = str(tmp_path / "c.enc")
    s = CredentialStore(p); s.set("zhipu", "sk-secret", master="pw123")
    assert b"sk-secret" not in open(p, "rb").read()
    assert s.status() == {"zhipu": True}

def test_wrong_master_rejected(tmp_path):
    s = CredentialStore(str(tmp_path / "c.enc")); s.set("zhipu", "k", master="good")
    with pytest.raises(CredentialError):
        s.get("zhipu", "bad")

def test_missing_provider(tmp_path):
    s = CredentialStore(str(tmp_path / "c.enc")); s.set("zhipu", "k", master="good")
    with pytest.raises(CredentialError):
        s.get("openai", "good")

def test_clear(tmp_path):
    p = str(tmp_path / "c.enc"); s = CredentialStore(p); s.set("zhipu", "k", master="g")
    s.clear()
    import os; assert not os.path.exists(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_credentials.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/credentials.py
import base64, json, os
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERS = 200_000

class CredentialError(Exception): pass

def _derive(master: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERS)
    return base64.urlsafe_b64encode(kdf.derive(master.encode()))

class CredentialStore:
    def __init__(self, path: str):
        self.path = path

    def _read(self) -> dict:
        if not os.path.exists(self.path):
            return {"salt": base64.b64encode(os.urandom(16)).decode(), "entries": {}}
        return json.loads(open(self.path).read())

    def _write(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        open(tmp, "w").write(json.dumps(data))
        os.replace(tmp, self.path)

    def set(self, provider: str, key: str, master: str) -> None:
        data = self._read()
        salt = base64.b64decode(data["salt"])
        data["entries"][provider] = Fernet(_derive(master, salt)).encrypt(key.encode()).decode()
        self._write(data)

    def get(self, provider: str, master: str) -> str:
        if not os.path.exists(self.path):
            raise CredentialError("no credential store")
        data = json.loads(open(self.path).read())
        if provider not in data.get("entries", {}):
            raise CredentialError(f"no key for {provider}")
        salt = base64.b64decode(data["salt"])
        try:
            return Fernet(_derive(master, salt)).decrypt(data["entries"][provider].encode()).decode()
        except InvalidToken as e:
            raise CredentialError("wrong master password or corrupt store") from e

    def status(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        return {p: True for p in json.loads(open(self.path).read()).get("entries", {})}

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_credentials.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/credentials.py tests/unit/test_credentials.py
git commit -m "feat(credentials): Fernet+PBKDF2 credential store, no plaintext"
```

---

## Task 12: Memory Store

**Files:**
- Create: `src/harness/memory/__init__.py` (empty), `src/harness/memory/store.py`
- Test: `tests/unit/test_memory.py`

**Interfaces:**
- Produces: `MemoryStore(notes_path: str, log_path: str)` with `.load_notes() -> str`, `.save_notes(text:str)`, `.append_log(entry: dict)`, `.recent_log(n:int) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_memory.py
from harness.memory.store import MemoryStore

def test_notes_roundtrip(tmp_path):
    m = MemoryStore(str(tmp_path / "notes.md"), str(tmp_path / "log.jsonl"))
    assert m.load_notes() == ""
    m.save_notes("run tests with: pytest")
    assert "pytest" in m.load_notes()

def test_log_append_and_recent(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l.jsonl"))
    m.append_log({"task": "t1", "outcome": "SUCCESS"})
    m.append_log({"task": "t2", "outcome": "STUCK"})
    assert m.recent_log(1) == [{"task": "t2", "outcome": "STUCK"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/memory/store.py
import json, os

class MemoryStore:
    def __init__(self, notes_path: str, log_path: str):
        self.notes_path = notes_path
        self.log_path = log_path

    def load_notes(self) -> str:
        return open(self.notes_path).read() if os.path.exists(self.notes_path) else ""

    def save_notes(self, text: str) -> None:
        open(self.notes_path, "w").write(text)

    def append_log(self, entry: dict) -> None:
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def recent_log(self, n: int) -> list[dict]:
        if not os.path.exists(self.log_path):
            return []
        return [json.loads(x) for x in open(self.log_path).read().splitlines()[-n:]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_memory.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/memory tests/unit/test_memory.py
git commit -m "feat(memory): file-backed notes + JSONL run-log store"
```

---

## Task 13: Test Runner (subprocess + junit + timeout)

**Files:**
- Create: `src/harness/tools/__init__.py` (empty), `src/harness/tools/runner.py`
- Test: `tests/unit/test_runner.py` (uses throwaway pytest projects in tmp_path)

**Interfaces:**
- Produces: `@dataclass TestRunOutput{exit_code:int; stdout:str; stderr:str; junit_xml:str}`; `run_tests(command: list[str], cwd: str, timeout: int, junit_path: str) -> TestRunOutput`. On timeout, `exit_code=124` and stderr contains `TimeoutExpired`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runner.py
from harness.tools.runner import run_tests, TestRunOutput

def _make_project(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_t.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n\ndef test_bad():\n    assert 1 + 1 == 3\n")

def test_runner_captures_exit_and_junit(tmp_path):
    _make_project(tmp_path)
    junit = str(tmp_path / "j.xml")
    out = run_tests(["pytest", "--junitxml", junit, "--tb=short", "tests/test_t.py"],
                    str(tmp_path), 30, junit)
    assert isinstance(out, TestRunOutput)
    assert out.exit_code == 1
    assert "<testsuite" in out.junit_xml

def test_runner_timeout(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_slow.py").write_text("import time\ndef test_slow():\n    time.sleep(5)\n")
    junit = str(tmp_path / "j.xml")
    out = run_tests(["pytest", "--junitxml", junit, "tests/test_slow.py"], str(tmp_path), 1, junit)
    assert out.exit_code == 124 and "TimeoutExpired" in out.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/tools/runner.py
import subprocess
from dataclasses import dataclass

@dataclass
class TestRunOutput:
    exit_code: int
    stdout: str
    stderr: str
    junit_xml: str

def run_tests(command: list[str], cwd: str, timeout: int, junit_path: str) -> TestRunOutput:
    try:
        p = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        xml = ""
        try:
            xml = open(junit_path).read()
        except FileNotFoundError:
            xml = ""
        return TestRunOutput(p.returncode, p.stdout, p.stderr, xml)
    except subprocess.TimeoutExpired as e:
        return TestRunOutput(124, e.stdout or "", f"subprocess.TimeoutExpired: {timeout}s", "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_runner.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/tools/runner.py src/harness/tools/__init__.py tests/unit/test_runner.py
git commit -m "feat(tools): pytest subprocess runner with junit capture + timeout"
```

---

## Task 14: Tool Dispatcher

**Files:**
- Create: `src/harness/tools/dispatcher.py`
- Test: `tests/unit/test_dispatcher.py`

**Interfaces:**
- Consumes: `Action` types (Task 1), `Config` (Task 8), `run_tests`/`TestRunOutput` (Task 13).
- Produces: `@dataclass ToolResult{ok:bool; stdout:str; stderr:str; exit_code:int; junit_xml:str}`; `ToolDispatcher(config: Config, test_runner=None)` with `.execute(action: Action) -> ToolResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_dispatcher.py
from harness.config import Config
from harness.tools.dispatcher import ToolDispatcher, ToolResult
from harness.actions.protocol import ReadFile, WriteFile, EditFile, RunShell, ListDir

def test_read_file(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("hi")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ReadFile("src/a.py"))
    assert r.ok and r.stdout == "hi"

def test_write_then_edit(tmp_path):
    (tmp_path / "src").mkdir()
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    assert d.execute(WriteFile("src/a.py", "old\n")).ok
    r = d.execute(EditFile("src/a.py", "old", "new"))
    assert r.ok and open(tmp_path / "src" / "a.py").read() == "new\n"

def test_edit_old_not_found(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(EditFile("src/a.py", "nope", "new"))
    assert r.ok is False and "not found" in r.stderr.lower()

def test_list_dir(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ListDir("src"))
    assert r.ok and "a.py" in r.stdout

def test_run_shell(tmp_path):
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(RunShell("echo hello"))
    assert r.ok and "hello" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_dispatcher.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/tools/dispatcher.py
import os, subprocess
from dataclasses import dataclass
from harness.actions.protocol import Action, ReadFile, ListDir, WriteFile, EditFile, RunShell, RunTests
from harness.config import Config
from harness.tools.runner import run_tests

@dataclass
class ToolResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    junit_xml: str = ""

class ToolDispatcher:
    def __init__(self, config: Config, test_runner=None):
        self.config = config
        self.test_runner = test_runner or run_tests

    def _abs(self, path: str) -> str:
        return os.path.join(self.config.project_root, path)

    def execute(self, action: Action) -> ToolResult:
        if isinstance(action, ReadFile):
            try:
                return ToolResult(True, open(self._abs(action.path)).read(), "", 0)
            except OSError as e:
                return ToolResult(False, "", str(e), 1)
        if isinstance(action, ListDir):
            try:
                return ToolResult(True, "\n".join(os.listdir(self._abs(action.path))), "", 0)
            except OSError as e:
                return ToolResult(False, "", str(e), 1)
        if isinstance(action, WriteFile):
            os.makedirs(os.path.dirname(self._abs(action.path)) or ".", exist_ok=True)
            open(self._abs(action.path), "w").write(action.content)
            return ToolResult(True, f"wrote {action.path}", "", 0)
        if isinstance(action, EditFile):
            p = self._abs(action.path)
            text = open(p).read()
            if action.old not in text:
                return ToolResult(False, "", "old block not found", 1)
            open(p, "w").write(text.replace(action.old, action.new, 1))
            return ToolResult(True, f"edited {action.path}", "", 0)
        if isinstance(action, RunShell):
            r = subprocess.run(action.command, cwd=self.config.project_root,
                               shell=True, capture_output=True, text=True)
            return ToolResult(r.returncode == 0, r.stdout, r.stderr, r.returncode)
        if isinstance(action, RunTests):
            junit = os.path.join(self.config.project_root, ".harness", "junit.xml")
            os.makedirs(os.path.dirname(junit), exist_ok=True)
            args = action.args.split() if action.args else []
            out = self.test_runner(["pytest", "--junitxml", junit, "--tb=short", *args],
                                   self.config.project_root, self.config.test_timeout_s, junit)
            return ToolResult(out.exit_code == 0, out.stdout, out.stderr, out.exit_code, out.junit_xml)
        return ToolResult(False, "", f"unknown action {type(action).__name__}", 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_dispatcher.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/tools/dispatcher.py tests/unit/test_dispatcher.py
git commit -m "feat(tools): ToolDispatcher executing read/list/write/edit/shell/run_tests"
```

---

## Task 15: Context Manager (engineered delivery layer)

**Files:**
- Create: `src/harness/context/__init__.py` (empty), `src/harness/context/manager.py`
- Test: `tests/unit/test_context_manager.py`

**Interfaces:**
- Consumes: `FailureReport` (Task 7), `MemoryStore` (Task 12).
- Produces: `@dataclass Message{role:str; content:str}`; `locate_impl_module(test_path: str) -> str | None` (static import trace); `ContextManager(config, memory)` with `.build_initial(task_test_path: str) -> list[Message]`, `.build(history: list[Message], last_feedback) -> list[Message]`. Bounded: keeps system + last K turns + feedback hint.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_context_manager.py
from harness.config import Config
from harness.memory.store import MemoryStore
from harness.context.manager import ContextManager, Message, locate_impl_module
from harness.feedback.types import FailureReport, FailureCategory

def _fb(cat=FailureCategory.LOGIC):
    return FailureReport(False, cat, ["t.test"], "HINTLINE", "tb", "4", "3", "sig", False)

def test_initial_context_has_system_and_protocol(tmp_path):
    (tmp_path/"tests").mkdir(); (tmp_path/"tests"/"t.py").write_text("def test_x(): assert 1==1\n")
    m = MemoryStore(str(tmp_path/"n"), str(tmp_path/"l"))
    cm = ContextManager(Config.default(), m); cm.config.project_root = str(tmp_path)
    msgs = cm.build_initial("tests/t.py")
    assert msgs[0].role == "system"
    assert any("ACTION:" in x.content for x in msgs)
    assert any("def test_x" in x.content for x in msgs)

def test_feedback_hint_is_emphasized(tmp_path):
    m = MemoryStore(str(tmp_path/"n"), str(tmp_path/"l"))
    cm = ContextManager(Config.default(), m); cm.config.project_root = str(tmp_path)
    msgs = cm.build([Message("assistant","old")], _fb())
    assert "HINTLINE" in msgs[-1].content

def test_history_is_bounded(tmp_path):
    m = MemoryStore(str(tmp_path/"n"), str(tmp_path/"l"))
    cm = ContextManager(Config.default(), m); cm.config.project_root = str(tmp_path)
    history = [Message("assistant", f"turn{i}") for i in range(10)]
    msgs = cm.build(history, _fb())
    joined = "\n".join(x.content for x in msgs)
    assert "turn9" in joined and "turn0" not in joined

def test_locate_impl_module_traces_import(tmp_path):
    (tmp_path/"src").mkdir(); (tmp_path/"src"/"foo.py").write_text("def add(a,b): return a-b\n")
    (tmp_path/"tests").mkdir(); (tmp_path/"tests"/"test_foo.py").write_text("from foo import add\n")
    assert locate_impl_module(str(tmp_path/"tests"/"test_foo.py")) == "src/foo.py"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_context_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/context/manager.py
import ast, os
from dataclasses import dataclass
from harness.config import Config
from harness.memory.store import MemoryStore

@dataclass
class Message:
    role: str
    content: str

_SYSTEM = """You are a TDD red-green fix agent. Make the failing test pass by editing source under the allowed scope.
Emit EXACTLY ONE action per turn using this protocol:

ACTION: <read_file|list_dir|write_file|edit_file|run_shell|run_tests|finish>
KEY: VALUE            # PATH: src/foo.py  /  ARGS: tests/t.py::test_x  /  COMMAND: ...
<<<TAG                 # content block (write_file: default; edit_file: <<<OLD / <<<NEW)
<literal content>
>>>TAG
Rules: prefer edit_file over write_file; run run_tests to verify; emit finish when green. One action per turn."""

def locate_impl_module(test_path: str) -> str | None:
    try:
        tree = ast.parse(open(test_path).read())
    except (OSError, SyntaxError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            guess = node.module.replace(".", "/") + ".py"
            if os.path.exists(guess):
                return guess
    return None

class ContextManager:
    def __init__(self, config: Config, memory: MemoryStore):
        self.config = config
        self.memory = memory

    def _read(self, rel: str) -> str:
        try:
            return open(os.path.join(self.config.project_root, rel)).read()
        except OSError:
            return f"<unreadable: {rel}>"

    def build_initial(self, task_test_path: str) -> list[Message]:
        msgs = [Message("system", _SYSTEM)]
        notes = self.memory.load_notes()
        if notes:
            msgs.append(Message("system", "Project notes:\n" + notes))
        impl = locate_impl_module(os.path.join(self.config.project_root, task_test_path))
        body = ["Failing test source (" + task_test_path + "):\n" + self._read(task_test_path)]
        if impl:
            body.append("Implementation under test (" + impl + "):\n" + self._read(impl))
        msgs.append(Message("user", "\n\n".join(body)))
        return msgs

    def build(self, history: list[Message], last_feedback) -> list[Message]:
        msgs = [history[0]] if history else [Message("system", _SYSTEM)]
        msgs += history[-self.config.max_history:]
        if last_feedback is not None and not getattr(last_feedback, "is_green", True):
            msgs.append(Message("user", "FEEDBACK (act on this):\n" + last_feedback.hint
                                + "\n" + last_feedback.traceback_excerpt))
        return msgs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_context_manager.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/context tests/unit/test_context_manager.py
git commit -m "feat(context): engineered delivery layer (selection/bounding/emphasis)"
```

---

## Task 16: LLM Client (protocol + mock)

**Files:**
- Create: `src/harness/llm/__init__.py` (empty), `src/harness/llm/base.py`, `src/harness/llm/mock.py`
- Test: `tests/unit/test_llm_mock.py`

**Interfaces:**
- Consumes: `Message` from Task 15.
- Produces: `LLMClient` Protocol (`.complete(messages: list[Message]) -> str`); `MockLLMClient(script: list[str] | callable)` returning scripted outputs in sequence (callable receives `messages`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_llm_mock.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_mock.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/llm/base.py
from typing import Protocol
from harness.context.manager import Message

class LLMClient(Protocol):
    def complete(self, messages: list[Message]) -> str: ...
```

```python
# src/harness/llm/mock.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_llm_mock.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/llm tests/unit/test_llm_mock.py
git commit -m "feat(llm): LLMClient protocol + MockLLMClient (offline test seam)"
```

---

## Task 17: AgentRunner Main Loop (integration)

**Files:**
- Create: `src/harness/agent.py`
- Test: `tests/integration/__init__.py` (empty), `tests/integration/test_agent_loop.py`

**Interfaces:**
- Consumes: everything above (`LLMClient`, `Config`, `ToolDispatcher`, `Guardrail`, `HITL`, `FeedbackEngine`, `ContextManager`, `parse_action`, `ParseError`, action types).
- Produces: `@dataclass Task{repo_path:str; test_selector:str}`; `@dataclass Turn{raw:str; action:str; decision:str; summary:str}`; `@dataclass RunResult{outcome:str; turns:list; edits_diff:str; failure_report}`; `AgentRunner(llm, config, dispatcher, guardrail, hitl, feedback_engine, context_manager)` with `.run(task) -> RunResult`. Outcomes ∈ {SUCCESS, STUCK, BUDGET_EXHAUSTED, HUMAN_ABORTED, ERROR}.

> **HUMAN_ABORTED wiring (T19) — final-review I1.** `HUMAN_ABORTED` is a SPEC §3.5-mandated terminal state ("HITL 否决到不可继续") that the current loop never emits: the `Approver` protocol returns `bool` (`ask -> allow/deny`), so a non-interactive `FailClosedApprover` maps every `AskHuman` to `Deny` and the loop continues to `BUDGET_EXHAUSTED`/`ERROR` instead of a terminal abort. `AgentRunner.HUMAN_ABORTED` is declared as a named constant and clearly marked PENDING interactive-wiring in `src/harness/agent.py`. Full abort semantics (a third `abort` verdict from `ConsoleApprover`, propagated through `HITL.request` to a terminal `RunResult`) are implemented in **T19** alongside the CLI/`ConsoleApprover` interactive path. This is deliberately deferred: there is no interactive Approver in the default non-interactive configuration, so wiring it now would be dead code with no test seam.

- [ ] **Step 1: Write the failing test (mock-LLM, real pytest on a tmp fixture)**

```python
# tests/integration/test_agent_loop.py
import textwrap
from harness.config import Config
from harness.memory.store import MemoryStore
from harness.context.manager import ContextManager
from harness.tools.dispatcher import ToolDispatcher
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.feedback.engine import FeedbackEngine
from harness.llm.mock import MockLLMClient
from harness.agent import AgentRunner, Task

def _repo(tmp_path, body):
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text(f"def add(a, b):\n    {body}\n")
    (tmp_path / "tests" / "test_foo.py").write_text("from foo import add\n\ndef test_add():\n    assert add(2,2) == 4\n")

def _runner(tmp_path, script, **overrides):
    cfg = Config.default(); cfg.project_root = str(tmp_path)
    cfg.dangerous_shell_patterns = [r"rm\s+-rf?"]; cfg.network_commands = ["pip install"]
    for k, v in overrides.items(): setattr(cfg, k, v)
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(cfg, mem)
    return AgentRunner(
        MockLLMClient(script), cfg, ToolDispatcher(cfg), Guardrail(cfg),
        HITL(FailClosedApprover()), FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n,
                                                   cfg.stuck_no_progress_m, cfg.hint_history_lines),
        cm)

EDIT = ("ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n"
        "<<<NEW\n    return a + b\n>>>NEW\n")
RT = "ACTION: run_tests\nARGS: tests/test_foo.py::test_add\n"
FIN = "ACTION: finish\nREASON: green\n"

def test_green_path_closes_feedback_loop(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, [RT, EDIT, RT, FIN]).run(Task(str(tmp_path), "tests/test_foo.py::test_add"))
    assert r.outcome == "SUCCESS"
    # the edit happened AFTER a failing run_tests (feedback drove the change)
    actions = [t.action for t in r.turns]
    assert "RunTests" in actions and "EditFile" in actions
    assert actions.index("EditFile") > actions.index("RunTests")
    assert "return a + b" in open(tmp_path / "src" / "foo.py").read()

def test_stuck_termination(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, [RT], stuck_repeat_n=3, max_iterations=99).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add"))
    assert r.outcome == "STUCK"

def test_budget_exhausted(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, [RT], stuck_repeat_n=99, stuck_no_progress_m=99, max_iterations=2).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add"))
    assert r.outcome == "BUDGET_EXHAUSTED"

def test_dangerous_action_denied_by_fail_closed(tmp_path):
    _repo(tmp_path, "return a - b")
    r = _runner(tmp_path, ["ACTION: run_shell\nCOMMAND: rm -rf /\n", FIN]).run(
        Task(str(tmp_path), "tests/test_foo.py::test_add"))
    decisions = [t.decision for t in r.turns]
    assert "Deny" in decisions  # fail-closed HITL denied the rm
    assert open(tmp_path / "src" / "foo.py").read().count("return") == 1  # file untouched by rm
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_agent_loop.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.agent`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/agent.py
import difflib, os
from dataclasses import dataclass, field
from harness.actions.parser import parse_action, ParseError
from harness.actions.protocol import Finish, RunTests
from harness.guardrails.guardrail import Allow, Deny, AskHuman

@dataclass
class Task:
    repo_path: str
    test_selector: str

@dataclass
class Turn:
    raw: str
    action: str
    decision: str
    summary: str

@dataclass
class RunResult:
    outcome: str
    turns: list = field(default_factory=list)
    edits_diff: str = ""
    failure_report: object = None

class AgentRunner:
    def __init__(self, llm, config, dispatcher, guardrail, hitl, feedback_engine, context_manager):
        self.llm = llm; self.config = config; self.dispatcher = dispatcher
        self.guardrail = guardrail; self.hitl = hitl
        self.feedback_engine = feedback_engine; self.context_manager = context_manager

    def _snapshot(self, path):
        p = os.path.join(self.config.project_root, path)
        try:
            return open(p).read().splitlines(keepends=True)
        except OSError:
            return []

    def run(self, task: Task) -> RunResult:
        before = {}
        for d in self.config.allowed_write_dirs:
            root = os.path.join(self.config.project_root, d)
            for dp, _, fs in os.walk(root):
                for f in fs:
                    rel = os.path.relpath(os.path.join(dp, f), self.config.project_root)
                    before[rel] = self._snapshot(rel)
        ctx = self.context_manager.build_initial(task.test_selector)
        turns, last_fb = [], None
        parse_failures = 0
        for _ in range(self.config.max_iterations):
            raw = self.llm.complete(ctx)
            try:
                action = parse_action(raw)
            except ParseError as e:
                parse_failures += 1
                turns.append(Turn(raw, "ParseError", "Deny", str(e)))
                ctx = self.context_manager.build(ctx + [__import__("harness.context.manager", fromlist=["Message"]).Message("assistant", raw)],
                                                  __fb_bad(str(e)))
                if parse_failures >= self.config.max_parse_failures:
                    return RunResult("ERROR", turns)
                continue
            decision = self.guardrail.check(action)
            summary = ""
            executed = False
            if isinstance(decision, AskHuman):
                decision = self.hitl.request(action, decision.reason)
            if isinstance(decision, Allow):
                result = self.dispatcher.execute(action)
                executed = True
                summary = (result.stdout + result.stderr)[:200]
                if isinstance(action, RunTests):
                    last_fb = self.feedback_engine.classify(result)
                    if last_fb.is_green:
                        turns.append(Turn(raw, type(action).__name__, "Allow", summary))
                        return self._finish("SUCCESS", turns, before)
                    if last_fb.stuck:
                        turns.append(Turn(raw, type(action).__name__, "Allow", summary))
                        return RunResult("STUCK", turns, self._diff(before), last_fb)
            elif isinstance(decision, Deny):
                summary = f"denied: {decision.reason}"
            turns.append(Turn(raw, type(action).__name__, type(decision).__name__, summary))
            if isinstance(action, Finish):
                return self._finish("SUCCESS" if (last_fb and last_fb.is_green) else "ERROR", turns, before)
            ctx = self.context_manager.build(ctx + [__import__("harness.context.manager", fromlist=["Message"]).Message("assistant", raw)], last_fb)
        return RunResult("BUDGET_EXHAUSTED", turns, self._diff(before), last_fb)

    def _finish(self, outcome, turns, before):
        return RunResult(outcome, turns, self._diff(before))

    def _diff(self, before):
        out = []
        for rel, old in before.items():
            new = self._snapshot(rel)
            if old != new:
                out.extend(difflib.unified_diff(old, new, fromfile=rel, tofile=rel))
        return "".join(out)
```

> Note: the inline `__import__` is to avoid a circular import (`agent` ↔ `context.manager`); a cleaner Task 17 cleanup is to import `Message` at top under `TYPE_CHECKING` or move `Message` to a tiny `harness/types.py`. Keep the minimal version for green, then refactor in Step 5.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_agent_loop.py -v`
Expected: PASS (4 tests). If the `__fb_bad` helper is missing, inline a tiny failure-shaped object instead (see refactor).

- [ ] **Step 5: Refactor — remove circular import smell**

Create `src/harness/types.py` exporting `Message` (move the dataclass there); import it in `context/manager.py` and `agent.py`. Replace `__import__(...)` calls with `from harness.types import Message` and replace `__fb_bad` with reusing `FailureReport(False, None, [], "parse error: ...", "", None, None, "", False)`. Re-run `pytest -m "not live" -q`.
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/harness/agent.py src/harness/types.py src/harness/context/manager.py tests/integration
git commit -m "feat(agent): AgentRunner main loop + mock-LLM integration tests (SUCCESS/STUCK/BUDGET/guardrail)"
```

---

## Task 18: Real GLM Client (gated live test)

**Files:**
- Create: `src/harness/llm/zhipu.py`
- Test: `tests/integration/test_zhipu_live.py` (marked `@pytest.mark.live`)

**Interfaces:**
- Consumes: `CredentialStore` (Task 11), `Message`.
- Produces: `ZhipuLLMClient(model: str, api_key: str)` with `.complete(messages) -> str` calling 智谱 GLM chat-completion via httpx.

- [ ] **Step 1: Write the failing test (skipped without key)**

```python
# tests/integration/test_zhipu_live.py
import os, pytest
from harness.llm.zhipu import ZhipuLLMClient
from harness.types import Message

@pytest.mark.live
def test_real_completion_returns_text():
    key = os.environ.get("ZHIPU_API_KEY")
    if not key:
        pytest.skip("ZHIPU_API_KEY not set")
    c = ZhipuLLMClient(model="glm-4.6", api_key=key)
    out = c.complete([Message("system", "Reply with the single word PONG."),
                      Message("user", "ping")])
    assert isinstance(out, str) and out.strip()
```

- [ ] **Step 2: Run test to verify it fails (or skips)**

Run: `pytest tests/integration/test_zhipu_live.py -v`
Expected: FAIL `ModuleNotFoundError` (module not yet created). With `-m "not live"` it is deselected.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/llm/zhipu.py
import httpx
from harness.types import Message

_BASE = "https://open.bigmodel.cn/api/paas/v4"

class ZhipuLLMClient:
    def __init__(self, model: str, api_key: str, base_url: str = _BASE):
        self.model = model; self.api_key = api_key; self.base_url = base_url

    def complete(self, messages: list[Message]) -> str:
        payload = {"model": self.model,
                   "messages": [{"role": m.role, "content": m.content} for m in messages]}
        r = httpx.post(f"{self.base_url}/chat/completions", json=payload,
                       headers={"Authorization": f"Bearer {self.api_key}"}, timeout=120)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
```

- [ ] **Step 4: Run default suite to confirm offline**

Run: `make test`
Expected: PASS — the live test is deselected by `-m "not live"`.

- [ ] **Step 5: Commit**

```bash
git add src/harness/llm/zhipu.py tests/integration/test_zhipu_live.py
git commit -m "feat(llm): real Zhipu GLM client (gated @pytest.mark.live)"
```

---

## Task 19: CLI (`harness init|key|fix`)

**Files:**
- Create: `src/harness/cli.py`
- Test: `tests/unit/test_cli.py` (subprocess-invokes the CLI; offline)

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands `init`, `key {status|set|clear}`, `fix --repo PATH --test SELECTOR [--config FILE]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli.py
import os, subprocess, sys
from harness.cli import main

def test_key_status_empty(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "zhipu" not in out  # nothing set yet

def test_init_then_status(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("getpass.getpass", lambda *_: "pw")
    monkeypatch.setattr("builtins.input", lambda *_: "sk-KEY")
    assert main(["init"]) == 0
    assert main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "zhipu" in out and "sk-KEY" not in out  # status, no plaintext
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/cli.py
import argparse, getpass, os, sys
from harness.config import load_config
from harness.credentials import CredentialStore, CredentialError

def _store():
    return CredentialStore(os.path.expanduser("~/.harness/credentials.enc"))

def _cmd_init(args):
    import getpass as gp
    master = gp.getpass("Choose master password: ")
    key = input("Paste your ZHIPU API key: ").strip()
    _store().set("zhipu", key, master)
    print("credentials stored (encrypted).")
    return 0

def _cmd_key(args):
    st = _store()
    if args.sub == "status":
        for provider, set_ in st.status().items():
            print(f"{provider}: {'set' if set_ else 'unset'}")
        if not st.status():
            print("(no keys stored)")
        return 0
    if args.sub == "set":
        master = getpass.getpass("Master password: ")
        key = input("New ZHIPU API key: ").strip()
        st.set("zhipu", key, master); print("updated."); return 0
    if args.sub == "clear":
        st.clear(); print("cleared."); return 0

def _cmd_fix(args):
    from harness.memory.store import MemoryStore
    from harness.context.manager import ContextManager
    from harness.tools.dispatcher import ToolDispatcher
    from harness.guardrails.guardrail import Guardrail
    from harness.guardrails.hitl import HITL, FailClosedApprover
    from harness.feedback.engine import FeedbackEngine
    from harness.agent import AgentRunner, Task
    cfg = load_config(args.config); cfg.project_root = args.repo
    mem = MemoryStore(os.path.join(args.repo, "HARNESS.md"), os.path.join(args.repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    runner = AgentRunner(None, cfg, ToolDispatcher(cfg), Guardrail(cfg), HITL(FailClosedApprover()),
                         FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m,
                                        cfg.hint_history_lines), cm)
    # wire real LLM only when key available
    try:
        master = os.environ.get("HARNESS_MASTER_PASSWORD") or getpass.getpass("Master password: ")
        key = _store().get("zhipu", master)
        from harness.llm.zhipu import ZhipuLLMClient
        runner.llm = ZhipuLLMClient("glm-4.6", key)
    except CredentialError:
        env_key = os.environ.get("ZHIPU_API_KEY")
        if not env_key:
            print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
        from harness.llm.zhipu import ZhipuLLMClient
        runner.llm = ZhipuLLMClient("glm-4.6", env_key)
    result = runner.run(Task(args.repo, args.test))
    print(f"OUTCOME: {result.outcome}")
    print(result.edits_diff)
    return 0 if result.outcome == "SUCCESS" else 1

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="harness")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=_cmd_init)
    pk = sub.add_parser("key"); pk.add_argument("sub", choices=["status", "set", "clear"]); pk.set_defaults(func=_cmd_key)
    pf = sub.add_parser("fix"); pf.add_argument("--repo", required=True); pf.add_argument("--test", required=True)
    pf.add_argument("--config", default=None); pf.set_defaults(func=_cmd_fix)
    args = p.parse_args(argv)
    return args.func(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/harness/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): harness init|key|fix with guided credential setup"
```

---

## Task 20: Mechanism Demo (§A.6)

**Files:**
- Create: `scripts/mechanism_demo.py`
- Test: `tests/integration/test_mechanism_demo.py` (asserts the script exits 0)

**Goal:** Deterministically reproduce, under mock LLM, the three §A.6 behaviors: ① guardrail intercepts a dangerous action; ② injected failure → feedback changes next action; ③ deep-dimension deterministic behavior (ENV vs LOGIC vs TIMEOUT vs stuck → different hints/outcomes).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_mechanism_demo.py
import subprocess, sys

def test_demo_runs_offline_and_exits_zero():
    r = subprocess.run([sys.executable, "scripts/mechanism_demo.py"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "①" in r.stdout and "②" in r.stdout and "③" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_mechanism_demo.py -v`
Expected: FAIL — file missing / non-zero.

- [ ] **Step 3: Write the demo (mock LLM + canned junit fixtures, no network)**

```python
# scripts/mechanism_demo.py
"""§A.6 deterministic mechanism demo. Runs fully offline with a mock LLM."""
from harness.config import Config
from harness.guardrails.guardrail import Guardrail, AskHuman
from harness.actions.protocol import RunShell
from harness.feedback.engine import FeedbackEngine
from harness.feedback.types import FailureCategory

GREEN_XML = '<?xml version="1.0"?><testsuite tests="1" failures="0" errors="0"><testcase name="t" classname="x"/></testsuite>'
ASSERT_XML = '<?xml version="1.0"?><testsuite tests="1" failures="1" errors="0"><testcase name="t" classname="x"><failure type="AssertionError" message="assert 3 == 4">assert 3 == 4</failure></testcase></testsuite>'
IMPORT_XML = '<?xml version="1.0"?><testsuite tests="0" failures="0" errors="1"><testcase name="c" classname="x"><error type="ModuleNotFoundError" message="No module named \'foo\'">x</error></testcase></testsuite>'

class TR:
    def __init__(self, exit_code, xml, stderr=""): self.exit_code = exit_code; self.junit_xml = xml; self.stderr = stderr; self.stdout = ""

def demo1_guardrail():
    cfg = Config.default(); cfg.dangerous_shell_patterns = [r"rm\s+-rf?"]
    g = Guardrail(cfg)
    d = g.check(RunShell("rm -rf /"))
    print("① guardrail intercept:", type(d).__name__, "-", getattr(d, "reason", ""))
    assert isinstance(d, AskHuman)

def demo2_feedback_changes_action():
    eng = FeedbackEngine(30, 99, 99, 8)
    fb = eng.classify(TR(1, ASSERT_XML))
    print("② feedback hint (drives next edit):", fb.hint.strip())
    assert "断言" in fb.hint  # the strategy tells the agent to fix logic, not touch deps

def demo3_categories_differ():
    eng = FeedbackEngine(30, 99, 99, 8)
    logic = eng.classify(TR(1, ASSERT_XML))
    env = eng.classify(TR(2, IMPORT_XML))
    timeout = eng.classify(TR(124, "", stderr="subprocess.TimeoutExpired: 30"))
    print("③ LOGIC:", logic.category.value, "| ENV:", env.category.value, "| TIMEOUT:", timeout.category.value)
    assert {logic.category, env.category, timeout.category} == {FailureCategory.LOGIC, FailureCategory.ENV, FailureCategory.TIMEOUT}

def main():
    print("=== §A.6 Mechanism Demo (offline, mock LLM) ===")
    demo1_guardrail(); demo2_feedback_changes_action(); demo3_categories_differ()
    print("=== all mechanism assertions passed ===")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_mechanism_demo.py -v && python scripts/mechanism_demo.py`
Expected: PASS; demo prints ①②③ and exits 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/mechanism_demo.py tests/integration/test_mechanism_demo.py
git commit -m "feat(demo): §A.6 deterministic mechanism demo (guardrail/feedback/categories)"
```

---

## Task 21: Thin WebUI (§五.9)

**Files:**
- Create: `web/app.py`, `web/templates/index.html`
- Test: `tests/integration/test_webui.py` (FastAPI TestClient, mock LLM)

**Interfaces:**
- Produces: FastAPI `app`; `GET /` returns the form; `POST /run` streams turns as SSE (one JSON line per turn + final outcome). Uses a mock LLM when no key is present (demo mode); fail-closed HITL.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_webui.py
from fastapi.testclient import TestClient
from web.app import app

def test_index_returns_form():
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and "<form" in r.text

def test_run_streams_turns(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def add(a,b):\n    return a-b\n")
    (tmp_path / "tests" / "test_foo.py").write_text("from foo import add\n\ndef test_add():\n    assert add(2,2)==4\n")
    monkeypatch.setenv("HARNESS_DEMO_REPO", str(tmp_path))
    c = TestClient(app)
    with c.stream("POST", "/run", json={"test": "tests/test_foo.py::test_add"}) as r:
        body = "\n".join(chunk for chunk in r.iter_text())
    assert "SUCCESS" in body or "RunTests" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_webui.py -v`
Expected: FAIL — `ModuleNotFoundError: web`.

- [ ] **Step 3: Write minimal implementation**

```python
# web/app.py
import json, os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Request
from pydantic import BaseModel
from harness.config import Config
from harness.memory.store import MemoryStore
from harness.context.manager import ContextManager
from harness.tools.dispatcher import ToolDispatcher
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.feedback.engine import FeedbackEngine
from harness.llm.mock import MockLLMClient
from harness.agent import AgentRunner, Task

app = FastAPI()

class RunReq(BaseModel):
    test: str

@app.get("/", response_class=HTMLResponse)
def index():
    return open("web/templates/index.html").read()

def _runner(repo: str):
    cfg = Config.default(); cfg.project_root = repo
    mem = MemoryStore(os.path.join(repo, "HARNESS.md"), os.path.join(repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    script = ["ACTION: run_tests\nARGS: {t}\n",
              "ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n<<<NEW\n    return a + b\n>>>NEW\n",
              "ACTION: run_tests\nARGS: {t}\n", "ACTION: finish\nREASON: green\n"]
    t = "tests/test_foo.py::test_add"
    return AgentRunner(MockLLMClient([s.format(t=t) for s in script]), cfg, ToolDispatcher(cfg),
                       Guardrail(cfg), HITL(FailClosedApprover()),
                       FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m,
                                       cfg.hint_history_lines), cm)

@app.post("/run")
def run(req: RunReq):
    repo = os.environ.get("HARNESS_DEMO_REPO", ".")
    runner = _runner(repo)
    def stream():
        result = runner.run(Task(repo, req.test))
        for t in result.turns:
            yield json.dumps({"turn": t.action, "decision": t.decision, "summary": t.summary}) + "\n"
        yield json.dumps({"outcome": result.outcome, "diff": result.edits_diff}) + "\n"
    return StreamingResponse(stream(), media_type="text/event-stream")
```

```html
<!-- web/templates/index.html -->
<!doctype html>
<html><head><meta charset="utf-8"><title>Harness Demo</title></head>
<body>
  <h1>Coding Agent Harness — TDD Red-Green Fixer</h1>
  <form id="f">
    <label>Failing test selector: <input name="test" value="tests/test_foo.py::test_add"></label>
    <button>Run</button>
  </form>
  <pre id="out"></pre>
  <script>
    document.getElementById('f').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const res = await fetch('/run', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({test: fd.get('test')})});
      const reader = res.body.getReader(); const dec = new TextDecoder();
      const out = document.getElementById('out');
      while (true) { const {value, done} = await reader.read(); if (done) break; out.textContent += dec.decode(value); }
    };
  </script>
</body></html>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_webui.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web tests/integration/test_webui.py
git commit -m "feat(web): thin FastAPI WebUI with SSE turn stream (§五.9)"
```

---

## Task 22: Distribution (Docker + PyPI + CI)

**Files:**
- Create: `Dockerfile`, `.gitlab-ci.yml`
- Test: `tests/integration/test_packaging.py` (builds wheel, asserts entrypoint importable)

**Interfaces:**
- Produces: buildable Docker image; installable wheel; CI with a `unit-test` job (§五.6) + image build (§4.8).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_packaging.py
import subprocess, sys, importlib.metadata as md

def test_package_importable():
    # installed via `pip install -e .` in bootstrap
    assert md.version("harness")

def test_console_script_exists():
    r = subprocess.run([sys.executable, "-c", "from harness.cli import main; print(callable(main))"],
                       capture_output=True, text=True)
    assert "True" in r.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_packaging.py -v`
Expected: FAIL if not installed editable; after `pip install -e ".[dev]"` → PASS. (Ensure bootstrap ran.)

- [ ] **Step 3: Write Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY web ./web
COPY scripts ./scripts
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["harness"]
```

- [ ] **Step 4: Write .gitlab-ci.yml**

```yaml
# .gitlab-ci.yml
image: python:3.11-slim

stages: [test, build]

unit-test:
  stage: test
  script:
    - pip install -e ".[dev]"
    - make test
  artifacts:
    reports:
      junit: .harness/junit.xml

build-image:
  stage: build
  image: docker:24
  services: [docker:24-dind]
  script:
    - docker build -t harness:latest .
    - docker run --rm harness key status
  only: [main]
```

- [ ] **Step 5: Run packaging test & verify docker builds**

Run: `pip install -e ".[dev]" && pytest tests/integration/test_packaging.py -v && docker build -t harness:ci . && docker run --rm harness key status`
Expected: test PASS; image builds; `key status` prints `(no keys stored)`.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile .gitlab-ci.yml tests/integration/test_packaging.py
git commit -m "ci: Dockerfile + .gitlab-ci.yml (unit-test job + image build)"
```

---

## Self-Review Notes (post-write)

- **Spec coverage:** all 13 SPEC sections map to tasks — feedback deep (T3–T7), governance (T9–T10), credentials (T11), distribution (T22), WebUI (T21), mechanism demo (T20). §10-U1 `allowed_write_dirs=["src"]` enforced in T0 example + T9 fence. §五.6 `unit-test` job in T22.
- **Circular import:** T17 introduces `harness/types.py` (Message) and refactors `context.manager` to import from it — execute that refactor or `Message` lookups break in agent.
- **Runner dependency note:** T13/T14/T17 tests spawn real `pytest` subprocesses (allowed — that's the target runner, not the LLM; still offline/no-network).
- **Live tests** (T18) deselected by `make test` (`-m "not live"`); default CI stays offline & deterministic per §A.6.
