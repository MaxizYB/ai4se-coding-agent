import ast
import os
import re

from harness.config import Config
from harness.memory.compactor import Compactor
from harness.memory.store import MemoryStore
from harness.types import Message

__all__ = ["ContextManager", "Message", "locate_impl_module"]

# M3: @mention file pull — matches `@<path>` tokens that look like file paths
# (must contain a dot delimiting an extension). Bare `@user` is NOT matched.
_MENTION_RE = re.compile(r"@([A-Za-z0-9_./\-]+\.[A-Za-z0-9]+)")

_SYSTEM = """You are a TDD red-green fix agent. Make the failing test pass by editing source under the allowed scope.
Emit EXACTLY ONE action per turn using this protocol:

ACTION: <read_file|list_dir|write_file|edit_file|run_shell|run_tests|finish>
KEY: VALUE            # PATH: src/foo.py  /  ARGS: tests/t.py::test_x  /  COMMAND: ...
<<<TAG                 # content block (write_file: default; edit_file: <<<OLD / <<<NEW)
<literal content>
>>>TAG
Rules: prefer edit_file over write_file; run run_tests to verify; emit finish when green. One action per turn."""

_CHAT_SYSTEM = """You are a coding agent working in the repository at {repo}.

Each turn, do exactly one of:
- Emit a tool action (one short line of prose, then the ACTION block) to make progress.
- Emit plain text with NO action — to answer a question, summarize, or ask the user. This ends your turn and returns control to the user.

Use tool actions to accomplish the task and verify with run_tests. When the task is done, or the user asked a question that needs no changes, reply in plain text (no ACTION). Do not emit `finish` to answer a question — just reply without an action. Only edit/write files when the user actually asked for a change; for "what is this project"-style questions, read and reply, do not modify anything.

ACTION protocol:
ACTION: <read_file|list_dir|write_file|edit_file|run_shell|run_tests|finish>
KEY: VALUE            # PATH: ... / ARGS: ... / COMMAND: ... / REASON: ...
<<<TAG                 # content block (write_file: <<< ... >>> ; edit_file: <<<OLD ... >>>OLD + <<<NEW ... >>>NEW)
<literal content>
>>>TAG

Exact examples (copy the format precisely):

  ACTION: read_file
  PATH: src/foo.py

  ACTION: list_dir
  PATH: src

  ACTION: write_file
  PATH: src/new.py
  print('hello')        # file content can be raw text after PATH (no fence needed),
  x = 1                 # OR a <<<...>>> block — either works.

  ACTION: edit_file
  PATH: src/foo.py
  <<<OLD
      return a - b
  >>>OLD
  <<<NEW
      return a + b
  >>>NEW

  ACTION: run_shell
  COMMAND: python src/game.py
  STDIN:
  5                      # stdin goes on the lines AFTER "STDIN:" (multi-line OK),
  3                      # so you can drive interactive programs that read input.
  7

  ACTION: run_tests
  ARGS: tests/test_foo.py::test_add

  ACTION: finish
  REASON: task complete

Rules:
- PATH is REQUIRED for read_file/write_file/edit_file; OPTIONAL for list_dir (omit to list the repo root).
- write_file: put file content after the PATH line (raw), or use a <<<...>>> block.
- Prefer edit_file over write_file for targeted changes; use write_file for new files.
- run_shell STDIN is optional — use it to feed input to interactive programs; omit for non-interactive commands.
- After editing, run run_tests to verify (when the project has tests).
- One action per turn when acting. Plain text with no ACTION = a reply that ends your turn.{accept}"""


def locate_impl_module(test_path: str) -> str | None:
    """Static import trace: parse `test_path`, find the first `from <pkg> import ...`
    whose target module resolves to a real file on disk, and return that file's
    path relative to the inferred project root (parent of the test directory).

    Search roots tried, in order: ``<root>/src``, ``<root>``, and the test file's
    own directory, where ``<root>`` is the parent of the directory holding the
    test (so ``<root>/tests/test_foo.py`` → ``<root>``). Returns ``None`` when no
    imported module can be located.
    """
    try:
        with open(test_path) as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return None
    test_dir = os.path.dirname(os.path.abspath(test_path))
    project_root = os.path.dirname(test_dir)
    search_roots = [
        os.path.join(project_root, "src"),
        project_root,
        test_dir,
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            rel = node.module.replace(".", "/") + ".py"
            for base in search_roots:
                candidate = os.path.join(base, rel)
                if os.path.exists(candidate):
                    return os.path.relpath(candidate, project_root)
    return None


class ContextManager:
    def __init__(self, config: Config, memory: MemoryStore):
        self.config = config
        self.memory = memory

    def _read(self, rel: str) -> str:
        try:
            with open(os.path.join(self.config.project_root, rel)) as f:
                return f.read()
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
        if not history:
            msgs = [Message("system", _SYSTEM)]
        else:
            # Retain a leading system message (role == "system") across the bound,
            # then keep only the last K turns so older history is dropped.
            head = [history[0]] if history[0].role == "system" else []
            tail = history[-self.config.max_history:]
            if head and tail[0] is history[0]:
                msgs = list(tail)
            else:
                msgs = head + tail
        if last_feedback is not None and not getattr(last_feedback, "is_green", True):
            msgs.append(
                Message(
                    "user",
                    "FEEDBACK (act on this):\n"
                    + last_feedback.hint
                    + "\n"
                    + last_feedback.traceback_excerpt,
                )
            )
        return msgs

    def build_chat(self, repo: str, accept: str | None, history: list[Message]) -> list[Message]:
        accept_line = f"\nAcceptance: the test '{accept}' passing (green) means success." if accept else ""
        system = Message("system", _CHAT_SYSTEM.format(repo=repo, accept=accept_line))
        msgs = [system]
        notes = self.memory.load_notes()
        if notes:
            msgs.append(Message("system", "Project notes:\n" + notes))
        agents_path = os.path.join(repo, "AGENTS.md")
        if os.path.exists(agents_path):
            try:
                with open(agents_path) as f:
                    agents_content = f.read()
            except OSError:
                agents_content = ""
            if agents_content:
                msgs.append(Message("system", "Project memory (AGENTS.md):\n" + agents_content))
        history = Compactor(self.config).maybe_compact(history)
        msgs += history[-self.config.max_history:]
        self._inject_mentions(msgs, repo)
        return msgs

    def _inject_mentions(self, msgs: list[Message], repo: str) -> None:
        """M3: pull content of files `@<path>`-mentioned in the last user
        message into context. Injection messages are inserted immediately
        after that user message so the agent sees them before its turn.
        Missing files are skipped; oversized files are truncated with a
        marker. Bounded by ``context_mention_max_files`` and deterministic.
        """
        last_user_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].role == "user":
                last_user_idx = i
                break
        if last_user_idx is None:
            return
        max_files = self.config.context_mention_max_files
        max_chars = self.config.context_mention_max_chars
        seen: set[str] = set()
        unique: list[str] = []
        for m in _MENTION_RE.findall(msgs[last_user_idx].content):
            if m not in seen:
                seen.add(m)
                unique.append(m)
                if len(unique) >= max_files:
                    break
        injections: list[Message] = []
        for mentioned in unique:
            path = os.path.join(repo, mentioned)
            if not (os.path.exists(path) and os.path.isfile(path)):
                continue
            try:
                with open(path) as f:
                    text = f.read()
            except OSError:
                continue
            if len(text) <= max_chars:
                body = text
            else:
                body = f"{text[:max_chars]}\n... [truncated, {len(text)} chars total]"
            injections.append(Message("user", f"<@{mentioned}>\n{body}"))
        if injections:
            msgs[last_user_idx + 1:last_user_idx + 1] = injections
