import ast
import os
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
