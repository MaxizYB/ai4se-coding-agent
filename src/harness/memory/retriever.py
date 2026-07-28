"""Self-implemented code retrieval (AST symbols + regex grep).

Stdlib-only code-retrieval helper (§A.4-D: memory storage+retrieval
self-implemented, no framework / vector DB). `symbols` walks a tree for
Python files and returns a name → location index built with `ast`; `grep`
walks text files and returns matching lines capped at `max_hits`. Both skip
the usual noise directories so a walk over the repo never descends into
caches, venvs, or nested worktrees. See task M4.
"""

from __future__ import annotations

import ast
import os
import re

__all__ = ["Retriever"]

# Directories pruned from every walk: build caches, VCS state, the harness
# scratch tree, nested worktrees, and virtualenvs.
_SKIP_DIRS = frozenset(
    {"__pycache__", ".git", ".harness", ".worktrees", "node_modules", ".venv", "venv"}
)

_TEXT_SUFFIXES = (".py", ".md", ".toml", ".txt", ".yml", ".yaml", ".json")

_SYMBOL_NODE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

_LINE_CAP = 160


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _iter_files(root: str, suffixes: tuple[str, ...]):
    """Yield files under root (sorted, skip-dirs pruned) matching a suffix."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(suffixes):
                yield os.path.join(dirpath, name)


class Retriever:
    """Stateless code-retrieval helpers (AST symbols + regex grep).

    Methods are static so they may be called as ``Retriever.symbols(root)``
    (namespace style) or via an instance ``Retriever().symbols(root)``; there
    is no per-instance state.
    """

    @staticmethod
    def symbols(root: str, max_files: int = 200) -> dict[str, list[str]]:
        """Index Python definitions under ``root``.

        Returns ``{name: ["<relpath>:<lineno>", ...]}`` for every
        ``FunctionDef`` / ``AsyncFunctionDef`` / ``ClassDef`` found via
        ``ast.walk``. At most ``max_files`` files are parsed; unparseable or
        unreadable files are skipped (never crash the walk).
        """
        index: dict[str, list[str]] = {}
        count = 0
        for path in _iter_files(root, (".py",)):
            if count >= max_files:
                break
            count += 1
            try:
                tree = ast.parse(_read(path), filename=path)
            except (SyntaxError, OSError, ValueError):
                continue
            relpath = os.path.relpath(path, root)
            for node in ast.walk(tree):
                if isinstance(node, _SYMBOL_NODE_TYPES):
                    index.setdefault(node.name, []).append(f"{relpath}:{node.lineno}")
        return index

    @staticmethod
    def grep(pattern: str, root: str, max_hits: int = 50) -> list[str]:
        """Regex search text files under ``root``.

        Returns up to ``max_hits`` entries of the form
        ``"<relpath>:<lineno>: <line trimmed to 160 chars>"``. Walks the text
        file suffixes only; unreadable files are skipped.
        """
        try:
            rx = re.compile(pattern)
        except re.error:
            return []  # M5: invalid regex — surface no hits, do not raise.
        hits: list[str] = []
        for path in _iter_files(root, _TEXT_SUFFIXES):
            try:
                lines = _read(path).splitlines()
            except OSError:
                continue
            relpath = os.path.relpath(path, root)
            for i, line in enumerate(lines, start=1):
                if rx.search(line):
                    hits.append(f"{relpath}:{i}: {line.strip()[:_LINE_CAP]}")
                    if len(hits) >= max_hits:
                        return hits
        return hits
