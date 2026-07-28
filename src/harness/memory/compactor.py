"""Deterministic conversation compaction (no LLM).

When history exceeds the configured char budget, older turns are collapsed
into ONE structured system message while the most recent K turns are kept
verbatim. Facts are extracted from action/observation lines; everything else
is reduced to a single truncated line so the compacted message stays small
and parseable. See task M1 (§A.4-C/D).
"""

from __future__ import annotations

import re

from harness.config import Config
from harness.types import Message

__all__ = ["Compactor"]

_FACT_LIMIT = 80
# M3: a prior compaction summary that ages into "old" and is re-compacted is
# preserved more fully than an ordinary fact (the 80-char cap would otherwise
# degrade the structured header across long sessions).
_SUMMARY_LIMIT = 500

# M6: line-anchored action match — "ACTION:" quoted mid-line (e.g. inside a
# FEEDBACK message) must NOT be classified as a real action.
_ACTION_LINE_RE = re.compile(r"(?m)^[ \t]*ACTION:\s*([A-Za-z_]\w*)")
# Per-line KEY: VALUE capture for the keys we surface as structured facts.
_KEY_RES = {key: re.compile(rf"(?m)^\s*{key}:\s*(.+?)\s*(?:#.*)?$") for key in ("PATH", "COMMAND", "ARGS")}


def _one_line(text: str) -> str:
    """Collapse whitespace (incl. newlines) to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text: str) -> str:
    return _one_line(text)[:_FACT_LIMIT]


def _action_fact(role: str, content: str) -> str:
    m = _ACTION_LINE_RE.search(content)
    parts = [f"{role}: {m.group(1)}"]
    for key in ("PATH", "COMMAND", "ARGS"):
        km = _KEY_RES[key].search(content)
        if km:
            parts.append(f"{key}={km.group(1).strip()}")
    return " ".join(parts)


class Compactor:
    """Compact a conversation history once it exceeds the char budget."""

    def __init__(self, config: Config):
        self.config = config

    def maybe_compact(self, history: list[Message]) -> list[Message]:
        if len(history) <= self.config.context_keep_recent:
            return history
        size = sum(len(m.content) for m in history)
        if size <= self.config.context_compact_threshold:
            return history
        keep = history[-self.config.context_keep_recent:]
        old = history[: -self.config.context_keep_recent]
        facts = [self._fact(m.role, m.content) for m in old]
        summary = Message("system", "[compacted history]\n" + "\n".join(facts))
        return [summary, *keep]

    def _fact(self, role: str, content: str) -> str:
        # M3: preserve a prior [compacted history] summary richly (don't crush
        # it to the 80-char fact cap) when it ages into "old" and is re-compacted.
        if content.startswith("[compacted history]"):
            body = content.split("[compacted history]\n", 1)[-1]
            return _one_line(body)[:_SUMMARY_LIMIT]
        # M6: only treat as an action when ACTION: begins a line.
        if _ACTION_LINE_RE.search(content):
            return _action_fact(role, content)
        return _truncate(content)
