# Governance Deep-Dim Implementation Plan (Sandbox + Diff-Preview + TaskReport)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Make governance the second deep dimension: an execution-level `Sandbox` (code-boundaries + optional Docker), write-before-apply diff preview/approval, and a structured `TaskReport` at task end.

**Architecture:** Add `Sandbox` (hard boundaries after the Guardrail's "ask" gate), `DiffPreviewer`/DiffGate (in the agent loops, before dispatcher mutates), `TaskReport` (from a structured `task_events` log the loops maintain). Kernel loops (chat.py/agent.py) gain these gates; dispatcher stays pure (no presentation). All deterministic, mock-testable (§A.4-B/C); Docker is opt-in integration.

**Tech Stack:** Python ≥3.11, stdlib (`re`,`os`,`difflib`,`ast`,`subprocess`); optional `docker` CLI.

## Global Constraints
- §A.4-B/C: every mechanism is deterministic code, mock/stub-testable, no network in default tests.
- TDD red→green→commit every task; `ruff check src tests scripts web` clean; `pytest -m "not live" -W error` green/pristine.
- Don't break existing 136 tests. `chat.py` is the primary mode; mirror gates into `agent.py` (fix mode) too.
- Reuse `Allow/Deny/AskHuman/GuardrailDecision` from `guardrails/guardrail.py`; add a `Containerize` decision.
- Default `sandbox.network = "allowlist"` (network cmds → AskHuman; practical for a coding agent). `offline` is the strict option.

---

## Task G1: `Sandbox` (denylist + network egress + write-roots)

**Files:** Create `src/harness/guardrails/sandbox.py`; modify `src/harness/config.py` (+ `[sandbox]` fields), `harness.toml.example`. Test `tests/unit/test_sandbox.py`.

**Interfaces:**
- Consumes `Action`/`RunShell`/`RunTests`/`WriteFile`/`EditFile`; `Config`; `Allow/Deny/AskHuman/GuardrailDecision` from guardrail.py.
- Produces: `Containerize(GuardrailDecision)`; `Sandbox(config).check(action) -> GuardrailDecision`.
- Config fields (defaults): `sandbox_network="allowlist"`, `sandbox_network_allow=[]`, `sandbox_denied_commands=[...]`, `sandbox_write_roots=["src"]`, `sandbox_containerize=False`, `sandbox_container_image="python:3.11-slim"`.

**Impl skeleton:**
```python
import os, re
from dataclasses import dataclass
from harness.actions.protocol import Action, RunShell, RunTests, WriteFile, EditFile
from harness.guardrails.guardrail import Allow, Deny, AskHuman, GuardrailDecision

@dataclass(frozen=True)
class Containerize(GuardrailDecision): pass

_NET_TOOLS = ["curl","wget","nc","ssh","scp","pip install","npm install","git clone","git push","git pull","http"]

class Sandbox:
    def __init__(self, config):
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
                if p.search(cmd): return Deny("sandbox: command matched denylist")
            net = self._network_tool(cmd)
            if net is not None:
                if self._net == "offline": return Deny(f"sandbox: network disabled (offline); uses '{net}'")
                if self._net == "allowlist" and net not in self._net_allow: return AskHuman(f"sandbox: network command '{net}'")
            return Containerize() if self.containerize else Allow()
        if isinstance(action, RunTests):
            return Containerize() if self.containerize else Allow()
        return Allow()

    def _in_write_root(self, path):
        root = os.path.abspath(self.config.project_root)
        ap = os.path.abspath(os.path.join(root, path))
        if not (ap == root or ap.startswith(root + os.sep)): return False
        return os.path.relpath(ap, root).split(os.sep)[0] in self._write_roots

    def _network_tool(self, cmd):
        for t in _NET_TOOLS:
            if re.search(rf"\b{re.escape(t)}\b", cmd): return t
        return None
```

**Tests:** deny `rm -rf /`; `curl` → Deny under offline, AskHuman under allowlist, Allow if in network_allow; write outside `src` → Deny / inside → Allow; `containerize=True` → `Containerize()` for RunShell/RunTests; safe `ls`/`pytest` → Allow.

- [ ] TDD steps (red→impl→green→commit `feat(guardrails): Sandbox — denylist + network egress + write-roots`).

---

## Task G2: wire `Sandbox` into the agent loops + Config

**Files:** Modify `src/harness/interactive/chat.py`, `src/harness/agent.py`, `src/harness/cli.py` (construct Sandbox), `src/harness/config.py` (defaults + load).

**Interfaces:** `ChatRunner.__init__(..., sandbox=None)`; `AgentRunner.__init__(..., sandbox=None)`. Loop order becomes: `guardrail.check → hitl(if AskHuman) → sandbox.check → hitl(if AskHuman) → (Containerize?→container exec else dispatcher.execute)`.

**Behavior change:** after the existing guardrail/hitl Allow, run `sandbox.check(action)`:
- `Deny` → `presenter.show_deny`/record + continue (same as guardrail Deny).
- `AskHuman` → `hitl.request` again.
- `Containerize` → route to `SandboxDockerExecutor` (G5; until G5 lands, treat as Allow with a TODO, or just Allow — wire the Containerize branch in G5).
- `Allow` → `dispatcher.execute`.

**Tests (integration):** extend `test_chat_runner.py` — `rm -rf /` with sandbox denylist → denied by sandbox (not guardrail); `curl` under allowlist + StubApprover(False) → denied; safe run_shell → runs. Use a StubApprover for the AskHuman path.

- [ ] TDD red→impl→green→commit `feat(agent): wire Sandbox gate into chat + fix loops`.

---

## Task G3: `DiffPreviewer` + DiffGate (write-before-apply approval)

**Files:** Create `src/harness/governance/diff_preview.py` (+ `governance/__init__.py`). Modify `interactive/presenter.py` (`show_diff`), `interactive/chat.py` + `agent.py` (DiffGate call), `config.py` (`diff_preview` ∈ always/ask/never, default ask).

**Interfaces:**
- `DiffPreviewer.preview(action, project_root) -> tuple[str, str]` `(path, unified_diff)`. WriteFile: before=current-or-""; after=content. EditFile: before=current; after=before.replace(old,new,1). Uses `difflib.unified_diff`.
- DiffGate (inline in the loop): for WriteFile/EditFile when `config.diff_preview=="ask"`: `path,diff=DiffPreviewer.preview(...)`; `presenter.show_diff(path,diff)`; `approved=approver.ask(...)`; skip if not approved. `"always"`: show + apply. `"never"`: apply silently. Non-interactive (`FailClosedApprover`) + ask → deny (don't apply without approval).

**Tests:** `DiffPreviewer.preview` snapshot (write new file → diff all-added; edit → old/new hunk); DiffGate with StubApprover(True/False) → applies/skips; non-interactive fail-closed → skip.

- [ ] TDD red→impl→green→commit `feat(governance): diff preview + approval gate before write/edit`.

---

## Task G4: `TaskReport` (structured end-of-task summary)

**Files:** Create `src/harness/governance/task_report.py`. Modify `interactive/presenter.py` (`show_report`), `interactive/chat.py` + `agent.py` (maintain `task_events`; build+show report at termination).

**Interfaces:**
- `task_events: list[dict]` — each `{kind:"file_changed"|"test"|"shell", detail, ok?}`. Loop appends: WriteFile/EditFile → `{"file_changed", path}`; RunShell → `{"shell", cmd, ok}`; RunTests → `{"test", selector, green}`.
- `TaskReport.build(task_events, outcome, agent_summary) -> dict` `{outcome, files_changed:[...], commands_run:[...], tests:[{selector,green}], summary}`.
- At Finish/SUCCESS/REPLIED/BUDGET: `report=TaskReport.build(...)`; `presenter.show_report(report)`.

**Tests:** feed canned task_events → assert aggregation (files_changed unique, tests green/red, commands list); chat integration: a read→edit→run_tests→finish run produces a report with the edited file + a test entry.

- [ ] TDD red→impl→green→commit `feat(governance): TaskReport — structured end-of-task summary`.

---

## Task G5: optional `SandboxDockerExecutor` (Containerize path)

**Files:** Create `src/harness/guardrails/sandbox_docker.py`. Modify `interactive/chat.py` + `agent.py` (Containerize branch), `config.py` (already has `sandbox_containerize`/`container_image`).

**Interfaces:** `SandboxDockerExecutor(config).run_shell(command, stdin="") -> ToolResult` and `.run_tests(args, junit_path) -> ToolResult` via `docker run --rm --network=none -v <repo>:/work -w /work <image> sh -c "<cmd>"`. The loop's Containerize branch calls these instead of `dispatcher.execute`.

**Tests (mock):** assert the constructed `docker run` args contain `--network=none`, the bind mount, and the image; uses an injected fake subprocess runner (no real docker). Real docker = opt-in integration (skip in default suite).

- [ ] TDD red→impl→green→commit `feat(guardrails): optional SandboxDockerExecutor for hard isolation`.

---

## Self-Review
- §A.4-D governance/sandbox covered (denylist+egress+FS + optional container). §A.4-B/C: all mock-testable; docker real-run is integration.
- `Containerize` decision + reuse of GuardrailDecision types — consistent across G1/G2/G5.
- DiffGate/TaskReport live in the loops (dispatcher stays pure) — consistent with guardrail/hitl placement.
- Defaults: `network=allowlist`, `diff_preview=ask`, `write_roots=["src"]` — practical for a general agent; `offline`/`never` available as strict options.
