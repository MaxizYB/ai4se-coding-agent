import os
import re
from dataclasses import dataclass

from harness.actions.protocol import Action, EditFile, RunShell, RunTests, WriteFile
from harness.config import Config
from harness.guardrails.guardrail import Allow, AskHuman, Deny, GuardrailDecision


@dataclass(frozen=True)
class Containerize(GuardrailDecision):
    pass


# Network egress tools; a hit means the command can talk to the network. Kept
# broad so a stray `pip install`/`git clone` cannot exfiltrate behind the shell.
_NET_TOOLS = [
    "curl",
    "wget",
    "nc",
    "ssh",
    "scp",
    "pip install",
    "npm install",
    "git clone",
    "git push",
    "git pull",
    "http",
]


class Sandbox:
    """HARD execution-boundary gate.

    Unlike Guardrail (which asks a human), the Sandbox denies outright: writes
    must land under a configured write-root, denylisted commands never run, and
    network egress is gated by ``sandbox_network``. When ``sandbox_containerize``
    is set, surviving shell/test actions are flagged ``Containerize`` so the
    runner executes them inside the configured image instead of the host.
    """

    def __init__(self, config: Config):
        self.config = config
        self._deny = [re.compile(p) for p in config.sandbox_denied_commands]
        self._net = config.sandbox_network
        self._net_allow = set(config.sandbox_network_allow)
        self._write_roots = config.sandbox_write_roots
        self.containerize = config.sandbox_containerize

    def check(self, action: Action) -> GuardrailDecision:
        if isinstance(action, (WriteFile, EditFile)):
            if not self._in_write_root(action.path):
                return Deny(f"sandbox: write outside write_roots {self._write_roots}: {action.path}")
            return Allow()
        if isinstance(action, RunShell):
            cmd = action.command
            for p in self._deny:
                if p.search(cmd):
                    return Deny("sandbox: command matched denylist")
            net = self._network_tool(cmd)
            if net is not None:
                if self._net == "offline":
                    return Deny(f"sandbox: network disabled (offline); command uses '{net}'")
                if self._net == "allowlist" and net not in self._net_allow:
                    return AskHuman(f"sandbox: network command '{net}'")
            return Containerize() if self.containerize else Allow()
        if isinstance(action, RunTests):
            return Containerize() if self.containerize else Allow()
        return Allow()

    def _in_write_root(self, path: str) -> bool:
        root = os.path.abspath(self.config.project_root)
        ap = os.path.abspath(os.path.join(root, path))
        if not (ap == root or ap.startswith(root + os.sep)):
            return False
        return os.path.relpath(ap, root).split(os.sep)[0] in self._write_roots

    def _network_tool(self, cmd: str) -> str | None:
        for t in _NET_TOOLS:
            if re.search(rf"\b{re.escape(t)}\b", cmd):
                return t
        return None
