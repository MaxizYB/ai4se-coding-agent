import os
import re
from dataclasses import dataclass

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
from harness.config import Config


@dataclass(frozen=True)
class GuardrailDecision: pass


@dataclass(frozen=True)
class Allow(GuardrailDecision): pass


@dataclass(frozen=True)
class Deny(GuardrailDecision): reason: str


@dataclass(frozen=True)
class AskHuman(GuardrailDecision): reason: str


def _compile_net(net: str) -> re.Pattern:
    # Word-bounded match for a network command phrase. The leading program name
    # may carry a version suffix (pip3, python3.12) so versioned tools are
    # caught too; digits/dots only keeps "curls"/"scurl" from matching "curl".
    parts = net.split()
    if not parts:
        return re.compile(r"^\b$")
    head = re.escape(parts[0]) + r"[\d.]*"
    tail = r"\s+".join(re.escape(p) for p in parts[1:])
    body = head + (r"\s+" + tail if tail else "")
    return re.compile(rf"\b{body}\b")


class Guardrail:
    def __init__(self, config: Config):
        self.config = config
        self._danger = [re.compile(p) for p in config.dangerous_shell_patterns]
        self._network = [_compile_net(net) for net in config.network_commands]

    def _in_scope(self, path: str) -> bool:
        root = os.path.realpath(self.config.project_root)
        ap = os.path.realpath(os.path.join(root, path))
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
            for net in self._network:
                if net.search(cmd):
                    return AskHuman(f"network/system command: {cmd}")
            return Allow()
        if isinstance(action, RunTests):
            return Allow()
        if isinstance(action, Finish):
            return Allow()
        return Deny(f"unknown action type: {type(action).__name__}")
