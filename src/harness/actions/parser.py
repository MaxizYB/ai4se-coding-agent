import re

from harness.actions.protocol import (
    Action,
    EditFile,
    Finish,
    ListDir,
    ReadFile,
    RunShell,
    RunTests,
    WriteFile,
)


class ParseError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# I5: trailing `\n?` (not required `\n`) so a final block at EOF with NO
# trailing newline still matches. Real LLMs frequently omit it; mock scripts
# always ended `\n` so the bug was masked.
_BLOCK = re.compile(r"<<<(?P<tag>[A-Z]*)\n(?P<body>.*?)>>>(?P=tag)\n?", re.DOTALL)
_ACTION_RE = re.compile(r"ACTION:\s*(?P<name>\w+)\b")

_SIMPLE = {
    "read_file": lambda p: ReadFile(p["PATH"]),
    "list_dir": lambda p: ListDir(p.get("PATH", ".")),  # PATH optional — defaults to repo root (cwd)
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


def _rest_after_param(tail: str, key: str) -> str | None:
    """Freedom fallback for write_file: if the LLM omits the <<<>>> block and
    just dumps file content after the `PATH:` line, return everything after
    that line. Real LLMs often write `ACTION: write_file\\nPATH: x\\n<content>`
    without the block fence -> old parser rejected it 3x before succeeding.
    """
    lines = tail.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.strip().startswith(key + ":"):
            return "".join(lines[i + 1 :])
    return None


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
            # Freedom: accept raw content dumped after the PATH line when the
            # LLM omits the <<<>>> block (common for large multi-line files).
            body = _rest_after_param(tail, "PATH")
        if body is None or body.strip() == "":
            raise ParseError("write_file requires content (a <<<>>> block OR raw text after the PATH line)")
        try:
            return WriteFile(params["PATH"], body)
        except KeyError as e:
            raise ParseError(f"missing parameter {e} for {name}") from e
    if name == "run_shell":
        # Freedom: STDIN is everything on the lines AFTER the `STDIN:` line
        # (multi-line, to drive interactive CLIs — e.g. feed moves to a game).
        stdin = _rest_after_param(tail, "STDIN") or ""
        try:
            return RunShell(params["COMMAND"], stdin)
        except KeyError as e:
            raise ParseError(f"missing parameter {e} for {name}") from e
    if name == "edit_file":
        old = blocks.get("OLD")
        new = blocks.get("NEW")
        if old is None or new is None:
            raise ParseError("edit_file requires <<<OLD and <<<NEW blocks")
        try:
            return EditFile(params["PATH"], old, new)
        except KeyError as e:
            raise ParseError(f"missing parameter {e} for {name}") from e
    builder = _SIMPLE.get(name)
    if builder is None:
        raise ParseError(f"unknown action: {name}")
    try:
        return builder(params)
    except KeyError as e:
        raise ParseError(f"missing parameter {e} for {name}") from e


def split_prose_and_action(text: str) -> tuple[str, "Action | None"]:
    """Split LLM output into (prose before ACTION:, parsed action).

    No ACTION: line -> (text.strip(), None) — a pure-narration turn.
    ACTION: present -> prose is the text before it; action = parse_action(text)
    (which may raise ParseError for malformed actions — the caller handles it).
    """
    m = _ACTION_RE.search(text)
    if m is None:
        return text.strip(), None
    return text[: m.start()].strip(), parse_action(text)
