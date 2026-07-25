# Interactive Chat CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Claude/Codex-style conversational REPL (`harness chat`) and a one-shot variant (`harness task`) on top of the existing harness kernel, so the agent freely modifies a project from natural-language instructions with inline HITL and visible feedback.

**Architecture:** A NEW self-contained `ChatRunner` (in `harness/interactive/`) drives its own loop and reuses the existing components directly (LLM/Parser/Dispatcher/Guardrail/HITL/FeedbackEngine/ContextManager). `AgentRunner.run()` (the batch `fix` loop) is NOT refactored — the two loops genuinely differ (presentation, termination, HITL approver, conversation vs single-task). `split_prose_and_action` exposes the LLM's "narration + action"; `ContextManager.build_chat` generalizes the system prompt; `Presenter` renders the REPL.

**Tech Stack:** Python ≥3.11, stdlib only for the interactive layer (ANSI text, `input`). Reuses pytest/cryptography/fastapi from the kernel.

## Global Constraints

- §A.4-C still holds: `ChatRunner`, `Presenter`, `split_prose_and_action`, `ContextManager.build_chat` must all be deterministic-unit-testable with `MockLLMClient` + fake input + spy/injected presenter — NO network in default tests.
- TDD hard requirement (red → green → commit) for every task.
- `ruff check src tests scripts web` clean; `python -m pytest -m "not live" -W error` green and pristine.
- The existing 108 tests MUST stay green (this plan is purely additive — it does not modify `AgentRunner.run()` behavior).
- Naming: new package `src/harness/interactive/` (avoids converting `cli.py` to a package; cli.py imports from it).
- Interactive HITL uses `ConsoleApprover` (`y/N`); non-interactive (`task`) uses `FailClosedApprover`.

---

## File Structure

```
src/harness/interactive/__init__.py     (empty)
src/harness/interactive/presenter.py    (Presenter — pure ANSI rendering to injected streams)
src/harness/interactive/chat.py         (ChatRunner — REPL + agent loop; reuses components)
src/harness/actions/parser.py           (MODIFY: add split_prose_and_action)
src/harness/context/manager.py          (MODIFY: add build_chat + _CHAT_SYSTEM)
src/harness/cli.py                       (MODIFY: register chat + task subcommands)
tests/unit/test_split_prose.py
tests/unit/test_presenter.py
tests/unit/test_build_chat.py
tests/integration/test_chat_runner.py
tests/unit/test_cli_chat_wiring.py
examples/demo/{src/foo.py,tests/test_foo.py,conftest.py}   (commit; runnable sample)
```

## Dependency & Order

T1 (split_prose), T2 (Presenter), T3 (build_chat) are independent leaves. T4 (ChatRunner) consumes T1+T2+T3. T5 (CLI wiring) consumes T4. T6 (docs/examples) last. Order: T1 → T2 → T3 → T4 → T5 → T6.

---

## Task 1: `split_prose_and_action`

**Files:**
- Modify: `src/harness/actions/parser.py` (add function at end)
- Test: `tests/unit/test_split_prose.py`

**Interfaces:**
- Consumes: `_ACTION_RE`, `parse_action` from the same module (T2 of the original PLAN).
- Produces: `split_prose_and_action(text: str) -> tuple[str, Action | None]`. Returns `(prose_before_action, action)`. If no `ACTION:` line → `(text.strip(), None)` (pure-prose turn). If `ACTION:` present → `(text[:start].strip(), parse_action(text))` (may raise `ParseError`, caller handles).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_split_prose.py
import pytest
from harness.actions.parser import split_prose_and_action, ParseError
from harness.actions.protocol import ReadFile, Finish

def test_prose_then_action():
    prose, action = split_prose_and_action("Let me read it.\nACTION: read_file\nPATH: x.py\n")
    assert prose == "Let me read it."
    assert action == ReadFile("x.py")

def test_pure_prose_no_action():
    prose, action = split_prose_and_action("Just thinking, no action this turn.")
    assert prose == "Just thinking, no action this turn."
    assert action is None

def test_action_only_no_prose():
    prose, action = split_prose_and_action("ACTION: finish\nREASON: done\n")
    assert prose == "" and action == Finish("done")

def test_multiline_prose():
    prose, action = split_prose_and_action("line one\nline two\nACTION: finish\nREASON: ok\n")
    assert prose == "line one\nline two" and action == Finish("ok")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_split_prose.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_prose_and_action'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/harness/actions/parser.py`:

```python
def split_prose_and_action(text: str) -> tuple[str, "Action | None"]:
    """Split LLM output into (prose before ACTION:, parsed action).

    No ACTION: line → (text.strip(), None) — a pure-narration turn.
    ACTION: present → prose is the text before it; action = parse_action(text)
    (which may raise ParseError for malformed actions — the caller handles it).
    """
    m = _ACTION_RE.search(text)
    if m is None:
        return text.strip(), None
    return text[: m.start()].strip(), parse_action(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_split_prose.py -v`
Expected: PASS (4 tests). Then `python -m pytest -m "not live" -q` — full suite still green.

- [ ] **Step 5: Commit**

```bash
git add src/harness/actions/parser.py tests/unit/test_split_prose.py
git commit -m "feat(actions): split_prose_and_action helper for chatty turns"
```

---

## Task 2: `Presenter`

**Files:**
- Create: `src/harness/interactive/__init__.py` (empty), `src/harness/interactive/presenter.py`
- Test: `tests/unit/test_presenter.py`

**Interfaces:**
- Consumes: `Action` types, `ToolResult` (from `harness.tools.dispatcher`), `FailureReport` (from `harness.feedback.types`).
- Produces: `Presenter(out=None)` writing ANSI text to `out` (default stdout). Methods: `welcome(repo, accept=None)`, `show_prose(text)`, `show_action(action, result)`, `show_feedback(fb)`, `show_deny(reason)`, `ask_human(action, reason) -> bool` (uses `input(...)`), `show_done(reason)`, `show_turn_end(outcome)`, `show_info(text)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_presenter.py
import io
from harness.interactive.presenter import Presenter
from harness.actions.protocol import ReadFile
from harness.tools.dispatcher import ToolResult
from harness.feedback.types import FailureReport, FailureCategory

def _fb():
    return FailureReport(False, FailureCategory.LOGIC, ["t.test"],
                         "断言失败：修实现逻辑。", "tb", "4", "3", "sig", False)

def test_snapshot():
    out = io.StringIO()
    p = Presenter(out=out)
    p.welcome("/repo", accept="tests/t.py::test_a")
    p.show_prose("I'll read the file.")
    p.show_action(ReadFile("x.py"), ToolResult(True, "file contents here", "", 0))
    p.show_feedback(_fb())
    p.show_deny("out-of-scope")
    p.show_done("test green")
    p.show_turn_end("SUCCESS")
    text = out.getvalue()
    assert "/repo" in text and "accept: tests/t.py::test_a" in text
    assert "I'll read the file." in text
    assert "ReadFile" in text and "file contents here" in text
    assert "LOGIC" in text and "修实现逻辑" in text
    assert "denied" in text and "out-of-scope" in text
    assert "done" in text and "test green" in text
    assert "SUCCESS" in text

def test_show_prose_empty_is_noop():
    out = io.StringIO(); Presenter(out=out).show_prose("")
    assert out.getvalue() == ""

def test_ask_human_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert Presenter(out=io.StringIO()).ask_human(ReadFile("x"), "reason") is True

def test_ask_human_default_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert Presenter(out=io.StringIO()).ask_human(ReadFile("x"), "reason") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_presenter.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.interactive.presenter`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/interactive/presenter.py
import sys
from harness.feedback.types import FailureReport


class Presenter:
    def __init__(self, out=None, err=None):
        self.out = out or sys.stdout
        self.err = err or sys.stderr

    def welcome(self, repo: str, accept: str | None = None) -> None:
        line = f"harness @ {repo}"
        if accept:
            line += f"  (accept: {accept})"
        self._write(f"{line}  — type your task, /help for commands")

    def show_prose(self, text: str) -> None:
        if text:
            self._write(text)

    def show_action(self, action, result) -> None:
        name = type(action).__name__
        summary = (result.stdout + result.stderr)[:200].replace("\n", " ")
        self._write(f"  -> {name}: {summary}")

    def show_feedback(self, fb: FailureReport) -> None:
        if fb is not None and not fb.is_green:
            self._write(f"  feedback [{fb.category.value}]: {fb.hint.strip()}")

    def show_deny(self, reason: str) -> None:
        self._write(f"  denied: {reason}")

    def ask_human(self, action, reason: str) -> bool:
        ans = input(f"  APPROVE {type(action).__name__}? {reason} [y/N]: ")
        return ans.strip().lower() == "y"

    def show_done(self, reason: str) -> None:
        self._write(f"  done: {reason}")

    def show_turn_end(self, outcome: str) -> None:
        self._write(f"  --- {outcome} ---")

    def show_info(self, text: str) -> None:
        self._write(text)

    def _write(self, s: str) -> None:
        self.out.write(s + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_presenter.py -v`
Expected: PASS (4 tests). Full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/harness/interactive tests/unit/test_presenter.py
git commit -m "feat(interactive): Presenter (ANSI REPL rendering to injected streams)"
```

---

## Task 3: `ContextManager.build_chat`

**Files:**
- Modify: `src/harness/context/manager.py` (add `_CHAT_SYSTEM` + `build_chat`)
- Test: `tests/unit/test_build_chat.py`

**Interfaces:**
- Consumes: `Message`, `MemoryStore`, `Config` (already in the module).
- Produces: `ContextManager.build_chat(repo: str, accept: str | None, history: list[Message]) -> list[Message]`. System prompt = chatty coding-agent instructions with the repo path and (optional) acceptance test; includes memory notes; appends the last `config.max_history` turns of `history`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_build_chat.py
from harness.config import Config
from harness.memory.store import MemoryStore
from harness.context.manager import ContextManager, Message

def test_build_chat_has_system_repo_and_accept(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat("/my/repo", "tests/t.py::test_a", [])
    assert msgs[0].role == "system"
    assert "/my/repo" in msgs[0].content
    assert "tests/t.py::test_a" in msgs[0].content
    assert "ACTION:" in msgs[0].content  # protocol reminder

def test_build_chat_no_accept_omits_acceptance(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(Config.default(), m)
    msgs = cm.build_chat("/repo", None, [])
    assert "Acceptance" not in msgs[0].content

def test_build_chat_includes_notes_and_bounds_history(tmp_path):
    m = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    m.save_notes("run tests with: pytest")
    cm = ContextManager(Config.default(), m); cm.config.max_history = 2
    history = [Message("user", f"turn{i}") for i in range(5)]
    msgs = cm.build_chat("/repo", None, history)
    joined = "\n".join(x.content for x in msgs)
    assert "pytest" in joined          # notes present
    assert "turn4" in joined and "turn0" not in joined  # bounded to last 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_build_chat.py -v`
Expected: FAIL — `AttributeError: 'ContextManager' object has no attribute 'build_chat'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/harness/context/manager.py` (inside the module, near `_SYSTEM`):

```python
_CHAT_SYSTEM = """You are a coding agent working in the repository at {repo}.
Accomplish the user's task. Each turn: say in ONE short line what you are doing, THEN emit exactly one action using this protocol:

ACTION: <read_file|list_dir|write_file|edit_file|run_shell|run_tests|finish>
KEY: VALUE            # PATH: ... / ARGS: ... / COMMAND: ... / REASON: ...
<<<TAG                 # content block (write_file: <<< ... >>> ; edit_file: <<<OLD ... >>>OLD + <<<NEW ... >>>NEW)
<literal content>
>>>TAG

Read files freely to explore. After editing, run run_tests to verify. Emit finish when the task is complete. Emit exactly one action per turn.{accept}"""


# inside class ContextManager:
    def build_chat(self, repo: str, accept: str | None, history: list[Message]) -> list[Message]:
        accept_line = f"\nAcceptance: the test '{accept}' passing (green) means success." if accept else ""
        system = Message("system", _CHAT_SYSTEM.format(repo=repo, accept=accept_line))
        msgs = [system]
        notes = self.memory.load_notes()
        if notes:
            msgs.append(Message("system", "Project notes:\n" + notes))
        msgs += history[-self.config.max_history:]
        return msgs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_build_chat.py -v`
Expected: PASS (3 tests). Full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/harness/context/manager.py tests/unit/test_build_chat.py
git commit -m "feat(context): build_chat — generalized chatty coding-agent prompt"
```

---

## Task 4: `ChatRunner`

**Files:**
- Create: `src/harness/interactive/chat.py`
- Test: `tests/integration/test_chat_runner.py`

**Interfaces:**
- Consumes: `split_prose_and_action` (T1), `Presenter` (T2), `ContextManager.build_chat` (T3), `ToolDispatcher`, `Guardrail` (`Allow`/`Deny`/`AskHuman`), `HITL`, `FeedbackEngine`, `Message`, `RunTests`/`Finish` actions.
- Produces: `ChatRunner(llm, config, dispatcher, guardrail, hitl, feedback_engine, context_manager, presenter=None, input_fn=None).run(repo, accept=None)`. REPL: reads user lines via `input_fn` (default `input`); per user message runs an inner agent loop until `Finish` / budget / (`--accept` green); renders via `presenter`; slash commands `/help /exit /clear /tests /status`.

- [ ] **Step 1: Write the failing test (mock LLM, real dispatcher+pytest on a tmp repo, fake input, spy Presenter)**

```python
# tests/integration/test_chat_runner.py
import io
from harness.config import Config
from harness.memory.store import MemoryStore
from harness.context.manager import ContextManager
from harness.tools.dispatcher import ToolDispatcher
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.feedback.engine import FeedbackEngine
from harness.llm.mock import MockLLMClient
from harness.interactive.presenter import Presenter
from harness.interactive.chat import ChatRunner

def _repo(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "tests" / "test_foo.py").write_text("from foo import add\n\ndef test_add():\n    assert add(2,2)==4\n")
    (tmp_path / "conftest.py").write_text("import os,sys\nsys.path.insert(0,os.path.join(os.path.dirname(__file__),'src'))\n")

def _runner(tmp_path, script, lines):
    cfg = Config.default(); cfg.project_root = str(tmp_path)
    cfg.dangerous_shell_patterns = [r"rm\s+-rf?"]; cfg.network_commands = ["pip install"]
    mem = MemoryStore(str(tmp_path / "n"), str(tmp_path / "l"))
    cm = ContextManager(cfg, mem)
    pres = Presenter(out=io.StringIO())
    r = ChatRunner(MockLLMClient(script), cfg, ToolDispatcher(cfg), Guardrail(cfg),
                   HITL(FailClosedApprover()),
                   FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines),
                   cm, pres, input_fn=lambda _p: next(lines))
    return r, pres

EDIT = ("ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n"
        "<<<NEW\n    return a + b\n>>>NEW\n")
RT = "ACTION: run_tests\nARGS: tests/test_foo.py::test_add\n"
FIN = "ACTION: finish\nREASON: test green\n"

def test_chat_read_edit_runtests_finish(tmp_path):
    _repo(tmp_path)
    script = ["Reading foo.\nACTION: read_file\nPATH: src/foo.py\n",
              "Fixing it.\n" + EDIT, "Verifying.\n" + RT, "Done.\n" + FIN]
    lines = iter(["make the test pass", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "Reading foo." in text and "Fixing it." in text and "Verifying." in text
    assert "ReadFile" in text and "EditFile" in text and "RunTests" in text
    assert "done" in text and "test green" in text
    assert "return a + b" in open(tmp_path / "src" / "foo.py").read()

def test_chat_accept_green_stops(tmp_path):
    _repo(tmp_path)
    script = ["Verifying.\n" + RT, "Done.\n" + FIN]
    lines = iter(["fix it", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept="tests/test_foo.py::test_add")
    # note: foo.py still a-b here so run_tests is RED; accept-stop only on green.
    # For a green path, pre-edit the file then run:
    assert "RunTests" in pres.out.getvalue()

def test_chat_accept_green_after_edit(tmp_path):
    _repo(tmp_path)
    script = ["Fix.\n" + EDIT, "Check.\n" + RT, FIN]   # FIN unused if accept stops first
    lines = iter(["fix", "/exit"])
    r, pres = _runner(tmp_path, script, lines)
    r.run(str(tmp_path), accept="tests/test_foo.py::test_add")
    assert "SUCCESS" in pres.out.getvalue()  # accept green stops with SUCCESS

def test_slash_clear_and_exit(tmp_path):
    _repo(tmp_path)
    lines = iter(["/clear", "/exit"])
    r, pres = _runner(tmp_path, [], lines)
    r.run(str(tmp_path), accept=None)
    text = pres.out.getvalue()
    assert "cleared" in text and "bye" in text
```

> Note for the implementer: `test_chat_accept_green_stops` and `test_chat_accept_green_after_edit` overlap — keep the cleaner one (the "after edit" green path) and drop the redundant one. The key assertions: (a) a full read→edit→run_tests→finish flow renders each step and edits the file; (b) `--accept` with a subsequent green `run_tests` stops with `SUCCESS` (no Finish needed); (c) `/clear` + `/exit` work.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_chat_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: harness.interactive.chat`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/harness/interactive/chat.py
from harness.actions.parser import split_prose_and_action, ParseError
from harness.actions.protocol import RunTests, Finish
from harness.guardrails.guardrail import Allow, Deny, AskHuman
from harness.interactive.presenter import Presenter
from harness.types import Message


class ChatRunner:
    def __init__(self, llm, config, dispatcher, guardrail, hitl,
                 feedback_engine, context_manager, presenter=None, input_fn=None):
        self.llm = llm
        self.config = config
        self.dispatcher = dispatcher
        self.guardrail = guardrail
        self.hitl = hitl
        self.feedback_engine = feedback_engine
        self.context_manager = context_manager
        self.presenter = presenter or Presenter()
        self.input_fn = input_fn or input

    def run(self, repo: str, accept: str | None = None) -> int:
        self.presenter.welcome(repo, accept)
        history: list[Message] = []
        while True:
            try:
                line = self.input_fn("> ")
            except (EOFError, KeyboardInterrupt):
                self.presenter.show_done("bye")
                return 0
            if line is None or line.strip() == "":
                continue
            if line.strip().startswith("/"):
                if self._slash(line.strip(), history):
                    return 0
                continue
            history.append(Message("user", line))
            outcome = self._agent_loop(repo, accept, history)
            self.presenter.show_turn_end(outcome)
            if outcome == "SUCCESS":
                # task satisfied; clear the completed turn's tool history, keep chatting
                history = [m for m in history if m.role == "user"][-1:]

    def _agent_loop(self, repo: str, accept: str | None, history: list[Message]) -> str:
        parse_failures = 0
        for _ in range(self.config.max_iterations):
            ctx = self.context_manager.build_chat(repo, accept, history)
            raw = self.llm.complete(ctx)
            try:
                prose, action = split_prose_and_action(raw)
            except ParseError as e:
                parse_failures += 1
                self.presenter.show_deny(f"parse error: {e.reason}")
                history.append(Message("assistant", raw))
                history.append(Message("user", f"your last output was not a valid action: {e.reason}; emit one ACTION per turn."))
                if parse_failures >= self.config.max_parse_failures:
                    return "ERROR"
                continue
            self.presenter.show_prose(prose)
            if action is None:
                history.append(Message("assistant", raw))
                continue  # pure narration; let the agent continue
            decision = self.guardrail.check(action)
            if isinstance(decision, AskHuman):
                decision = Allow() if self.presenter.ask_human(action, decision.reason) else Deny("human denied")
            if isinstance(decision, Deny):
                self.presenter.show_deny(decision.reason)
                history.append(Message("assistant", raw))
                history.append(Message("user", f"action denied: {decision.reason}; try a different approach."))
                continue
            result = self.dispatcher.execute(action)
            self.presenter.show_action(action, result)
            obs = (result.stdout + "\n" + result.stderr)[-2000:]
            if isinstance(action, RunTests):
                fb = self.feedback_engine.classify(result)
                self.presenter.show_feedback(fb)
                history.append(Message("assistant", raw))
                history.append(Message("user", "OBSERVATION:\n" + obs + "\nFEEDBACK:\n" + fb.hint + "\n" + fb.traceback_excerpt))
                if accept and accept in action.args and fb.is_green:
                    self.presenter.show_done(f"acceptance test green: {accept}")
                    return "SUCCESS"
                continue
            if isinstance(action, Finish):
                self.presenter.show_done(action.reason)
                return "FINISH"
            history.append(Message("assistant", raw))
            history.append(Message("user", "OBSERVATION:\n" + obs))
        return "BUDGET_EXHAUSTED"

    def _slash(self, cmd: str, history: list[Message]) -> bool:
        """Return True if the REPL should exit."""
        c = cmd.lower()
        if c in ("/exit", "/quit"):
            self.presenter.show_done("bye")
            return True
        if c == "/clear":
            history.clear()
            self.presenter.show_info("(context cleared)")
            return False
        if c == "/help":
            self.presenter.show_info("commands: /help /exit /clear /tests [selector] /status\nactions: read_file list_dir write_file edit_file run_shell run_tests finish")
            return False
        if c.startswith("/tests"):
            args = cmd[len("/tests"):].strip()
            r = self.dispatcher.execute(RunTests(args))
            self.presenter.show_action(RunTests(args), r)
            fb = self.feedback_engine.classify(r)
            self.presenter.show_feedback(fb)
            return False
        if c == "/status":
            self.presenter.show_info(f"budget max_iterations={self.config.max_iterations}; history={len(history)} msgs")
            return False
        self.presenter.show_info(f"unknown command: {cmd} (/help for list)")
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/integration/test_chat_runner.py -v`
Expected: PASS (the kept tests). Full suite green (`python -m pytest -m "not live" -q`).

- [ ] **Step 5: Commit**

```bash
git add src/harness/interactive/chat.py tests/integration/test_chat_runner.py
git commit -m "feat(interactive): ChatRunner REPL — chatty agent loop, HITL, slash commands"
```

---

## Task 5: CLI registration (`harness chat` / `harness task`)

**Files:**
- Modify: `src/harness/cli.py` (add `_cmd_chat`, `_cmd_task`; register subparsers)
- Test: `tests/unit/test_cli_chat_wiring.py`

**Interfaces:**
- Consumes: `ChatRunner` (T4), `ConsoleApprover`/`FailClosedApprover`, existing `_resolve_llm`-style credential logic in `_cmd_fix` (extract if needed), `load_config`, `ContextManager`, `ToolDispatcher`, `Guardrail`, `HITL`, `FeedbackEngine`, `MemoryStore`.
- Produces: `main(["chat", "--repo", PATH, "--accept", TEST?, "--config", FILE?]) -> int` (interactive, `ConsoleApprover`) and `main(["task", "--repo", PATH, "--goal", "...", "--accept", TEST?]) -> int` (non-interactive, `FailClosedApprover`; sends the goal as the first user message then runs once). No-creds → return 2.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli_chat_wiring.py
from harness.cli import main

def test_chat_no_creds_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    rc = main(["chat", "--repo", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "cred" in err.lower() or "key" in err.lower()

def test_chat_wires_chatrunner(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    called = {}
    class FakeRunner:
        def __init__(self, *a, **k): pass
        def run(self, repo, accept=None): called["run"] = (repo, accept); return 0
    monkeypatch.setattr("harness.interactive.chat.ChatRunner", FakeRunner)
    rc = main(["chat", "--repo", str(tmp_path), "--accept", "tests/t.py::test_a"])
    assert rc == 0 and called["run"] == (str(tmp_path), "tests/t.py::test_a")

def test_task_wires_chatrunner_failclosed(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    called = {}
    class FakeRunner:
        def __init__(self, *a, **k): pass
        def run_task(self, repo, goal, accept=None): called["run_task"] = (goal, accept); return 0
    monkeypatch.setattr("harness.interactive.chat.ChatRunner", FakeRunner)
    rc = main(["task", "--repo", str(tmp_path), "--goal", "fix the bug", "--accept", "tests/t.py::test_a"])
    assert rc == 0 and called["run_task"] == ("fix the bug", "tests/t.py::test_a")
```

> Implementer note: the test asserts `ChatRunner` is the wiring seam. Either (a) add `ChatRunner.run_task(repo, goal, accept=None)` that seeds one user message and runs non-interactively (FailClosed), or (b) `task` constructs ChatRunner and calls a dedicated one-shot entry. Pick (a) for symmetry. If you choose a different seam name, update the test to match — the requirement is: `task` is non-interactive (FailClosed), `chat` is interactive (Console), both reuse ChatRunner, both honor `--accept`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_cli_chat_wiring.py -v`
Expected: FAIL — `chat`/`task` subcommands not recognized (argparse error) or `ChatRunner` not wired.

- [ ] **Step 3: Write minimal implementation**

In `src/harness/cli.py`:

```python
def _resolve_llm():
    """Return (llm_client_or_None). Encrypted store first (master pw), then ZHIPU_API_KEY env."""
    import os, getpass as gp
    from harness.credentials import CredentialStore, CredentialError
    st = CredentialStore(os.path.expanduser("~/.harness/credentials.enc"))
    try:
        master = os.environ.get("HARNESS_MASTER_PASSWORD") or gp.getpass("Master password: ")
        from harness.llm.zhipu import ZhipuLLMClient
        return ZhipuLLMClient("glm-4.6", st.get("zhipu", master))
    except CredentialError:
        env_key = os.environ.get("ZHIPU_API_KEY")
        if env_key:
            from harness.llm.zhipu import ZhipuLLMClient
            return ZhipuLLMClient("glm-4.6", env_key)
        return None


def _build_chat_components(args):
    from harness.config import load_config
    from harness.memory.store import MemoryStore
    from harness.context.manager import ContextManager
    from harness.tools.dispatcher import ToolDispatcher
    from harness.guardrails.guardrail import Guardrail
    from harness.feedback.engine import FeedbackEngine
    cfg = load_config(getattr(args, "config", None)); cfg.project_root = args.repo
    mem = MemoryStore(os.path.join(args.repo, "HARNESS.md"), os.path.join(args.repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    fe = FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines)
    return cfg, ToolDispatcher(cfg), Guardrail(cfg), fe, cm


def _cmd_chat(args):
    import sys
    from harness.guardrails.hitl import HITL, ConsoleApprover
    from harness.interactive.chat import ChatRunner
    llm = _resolve_llm()
    if llm is None:
        print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
    cfg, disp, gr, fe, cm = _build_chat_components(args)
    ChatRunner(llm, cfg, disp, gr, HITL(ConsoleApprover()), fe, cm).run(args.repo, accept=args.accept)
    return 0


def _cmd_task(args):
    import sys
    from harness.guardrails.hitl import HITL, FailClosedApprover
    from harness.interactive.chat import ChatRunner
    llm = _resolve_llm()
    if llm is None:
        print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
    cfg, disp, gr, fe, cm = _build_chat_components(args)
    runner = ChatRunner(llm, cfg, disp, gr, HITL(FailClosedApprover()), fe, cm)
    return runner.run_task(args.repo, args.goal, accept=args.accept)
```

And add to `ChatRunner` (T4) a `run_task`:
```python
    def run_task(self, repo: str, goal: str, accept: str | None = None) -> int:
        self.presenter.welcome(repo, accept)
        history = [Message("user", goal)]
        outcome = self._agent_loop(repo, accept, history)
        self.presenter.show_turn_end(outcome)
        return 0 if outcome in ("SUCCESS", "FINISH") else 1
```

Register subparsers in `main()`:
```python
    pc = sub.add_parser("chat"); pc.add_argument("--repo", required=True)
    pc.add_argument("--accept", default=None); pc.add_argument("--config", default=None)
    pc.set_defaults(func=_cmd_chat)
    pt = sub.add_parser("task"); pt.add_argument("--repo", required=True)
    pt.add_argument("--goal", required=True); pt.add_argument("--accept", default=None)
    pt.add_argument("--config", default=None); pt.set_defaults(func=_cmd_task)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_cli_chat_wiring.py -v`
Expected: PASS (3 tests). Full suite green; `ruff check src tests scripts web` clean.

- [ ] **Step 5: Commit**

```bash
git add src/harness/cli.py src/harness/interactive/chat.py tests/unit/test_cli_chat_wiring.py
git commit -m "feat(cli): harness chat (interactive) + task (one-shot) subcommands"
```

---

## Task 6: Runnable example + README

**Files:**
- Create: `examples/demo/{src/foo.py, tests/test_foo.py, conftest.py}` (already on disk untracked — verify + commit)
- Modify: `README.md` (add "Conversational CLI" section), `AGENT_LOG.md` (append the chat-CLI PR line)

**Interfaces:** none (docs/example).

- [ ] **Step 1: Verify the example repo is red (sanity)**

Run: `python -m pytest examples/demo/tests/test_foo.py -q`
Expected: 1 failed (`assert 0 == 4` — `add` returns `a - b`).

- [ ] **Step 2: Add README "Conversational CLI" section**

Insert after the "## Run" section in `README.md`:

```markdown
### Conversational REPL (Claude/Codex-style)
```bash
export ZHIPU_API_KEY="<your GLM key>"
harness chat --repo /path/to/project            # multi-turn; type tasks, /help for commands
harness chat --repo /path/to/project --accept tests/test_foo.py::test_add   # stop when green
harness task --repo /path/to/project --goal "add a login function"          # one-shot, non-interactive
```
The agent narrates each step, reads/edits files, runs tests to self-check (failure class + hint shown inline), and asks `y/N` before dangerous/network actions. Try it on the bundled sample:
```bash
harness chat --repo examples/demo --accept tests/test_foo.py::test_add
```
```

- [ ] **Step 3: Append AGENT_LOG entry**

Add to `AGENT_LOG.md` (new Phase after Phase 7): `## Phase 8 — 范围纠偏:对话式 CLI (feat/chat)` with a one-line summary: brainstorming → SPEC delta (commit 86c7b72) → this plan → ChatRunner/Presenter/build_chat/split_prose → merge.

- [ ] **Step 4: Final verification**

Run: `make test && make lint && make demo`
Expected: all green (test count = 108 + new tests from T1–T5); ruff clean; demo ①②③.

- [ ] **Step 5: Commit**

```bash
git add examples/demo README.md AGENT_LOG.md
git commit -m "docs: runnable examples/demo + README conversational-CLI section + AGENT_LOG phase 8"
```

---

## Self-Review Notes

- **Spec coverage:** design-delta §2 (architecture: ChatRunner reuses components, AgentRunner.run untouched) ✓; §3 REPL loop = T4 ✓; §4 build_chat = T3 ✓; §5 Presenter = T2 ✓; §6 slash commands = T4 `_slash` ✓; §7 HITL/termination = T4+T5 ✓; §8 testing = each task has mock/fake-input tests ✓; §9 file list = matches (using `interactive/` package instead of `cli/` subpackage — noted deviation, avoids converting cli.py).
- **No AgentRunner.run refactor** — the batch loop is untouched; the 108 existing tests stay green by construction. ChatRunner has its own loop (genuine divergence in termination/presentation/approver justifies it).
- **Type consistency:** `split_prose_and_action -> tuple[str, Action|None]` (T1) consumed identically in T4; `Presenter` method names (T2) match T4/T5 calls; `build_chat(repo, accept, history)` (T3) matches T4 calls; `ChatRunner.run`/`run_task` (T4) match T5 wiring tests.
- **Known follow-up (not in this plan):** `--accept` detection keys on `accept in action.args` (the RunTests ARGS); if the agent runs the full suite instead of the selector, green won't auto-stop. Acceptable for v1; the system prompt tells the agent to run the acceptance test.
