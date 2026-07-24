import os
import re
from dataclasses import dataclass

from harness.actions.protocol import (
    Action,
    EditFile,
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
