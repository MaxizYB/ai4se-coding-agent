import os
import re
from dataclasses import dataclass

from harness.actions.protocol import Action, EditFile, RunShell, RunTests, WriteFile
from harness.config import Config
from harness.guardrails.guardrail import (
    Allow,
    AskHuman,
    Deny,
    GuardrailDecision,
    network_tool_match,
)


@dataclass(frozen=True)
class Containerize(GuardrailDecision):
    pass


# Network egress tool phrases; a hit means the command can talk to the network.
# Kept broad so a stray `pip install`/`git clone` cannot exfiltrate behind the
# shell. Matched via the shared `network_tool_match` (version-suffix + \s+), the
# SAME matcher the soft Guardrail uses, so neither gate is weaker than the other.
# NOTE: the bare "http" entry was REMOVED — it false-matched `grep http` /
# `git config http.` and was never a tool name. Raw URLs are caught separately
# via the `https?://` check below (see `_network_tool`).
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
]

# A raw URL signals egress intent even when no known tool name is present (e.g.
# `python -c "urllib.request.urlopen('https://...")`). Caught only in the Sandbox
# (the HARD boundary); the soft Guardrail stays tool-phrase-only so it does not
# over-trigger AskHuman on harmless prose.
_URL_RE = re.compile(r"https?://")


class Sandbox:
    """HARD execution-boundary gate.

    Unlike Guardrail (which asks a human), the Sandbox denies outright: writes
    must land under a configured write-root, denylisted commands never run, and
    network egress is gated by ``sandbox_network``. When ``sandbox_containerize``
    is set, surviving shell/test actions are flagged ``Containerize`` so the
    runner executes them inside the configured image instead of the host.

    NOTE on shell writes: FS write-scope (``write_roots``) is enforced ONLY for
    WriteFile/EditFile actions. An arbitrary ``RunShell`` command can write
    ANYWHERE via redirection (``>``), ``sed -i``/``cp``/``mv``, or a script — the
    denylist above is a cheap mitigation (``rm -rf``, ``sed -i`` are denied), not
    a complete fence. For HARD filesystem isolation set
    ``sandbox_containerize = true`` (Docker ``--read-only`` + bind-mount). Full
    shell-write analysis is out of scope here.
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
        # The Sandbox is the HARD boundary, so it must be at least as strict as
        # the Guardrail: resolve symlinks via realpath (not abspath). A lexical
        # abspath leaves `src/link -> /tmp/outside` intact and smuggles a write
        # out of the fence; realpath resolves the link and the escape is Denied.
        root = os.path.realpath(self.config.project_root)
        ap = os.path.realpath(os.path.join(root, path))
        if not (ap == root or ap.startswith(root + os.sep)):
            return False
        return os.path.relpath(ap, root).split(os.sep)[0] in self._write_roots

    def _network_tool(self, cmd: str) -> str | None:
        # Shared matcher (version-suffix + \s+); identical strength to the
        # Guardrail so neither gate is weaker. See network_tool_match.
        hit = network_tool_match(cmd, _NET_TOOLS)
        if hit is not None:
            return hit
        # Fall back to a raw URL — egress intent with no recognized tool name.
        if _URL_RE.search(cmd):
            return "http(s)://"
        return None
