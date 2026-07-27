import difflib
import os
from dataclasses import dataclass, field

from harness.actions.parser import ParseError, parse_action
from harness.actions.protocol import Finish, RunTests
from harness.feedback.types import FailureReport
from harness.guardrails.guardrail import Allow, AskHuman, Deny
from harness.guardrails.sandbox import Containerize
from harness.types import Message


@dataclass
class Task:
    repo_path: str
    test_selector: str


@dataclass
class Turn:
    raw: str
    action: str
    decision: str
    summary: str


@dataclass
class RunResult:
    outcome: str
    turns: list = field(default_factory=list)
    edits_diff: str = ""
    failure_report: object = None


class AgentRunner:
    # Outcomes (SPEC §3.5): SUCCESS / STUCK / BUDGET_EXHAUSTED / ERROR are
    # emitted by run() below. HUMAN_ABORTED (SPEC §3.5: "HITL 否决到不可继续")
    # is PENDING interactive-wiring -- it requires an abort signal from an
    # interactive Approver (ConsoleApprover returning a third "abort" verdict,
    # not just allow/deny). The current Approver contract returns bool
    # (ask->allow/deny), so a non-interactive FailClosedApprover maps every
    # AskHuman to Deny and the loop continues (BUDGET_EXHAUSTED/ERROR), never
    # reaching a terminal abort. Full abort semantics are wired in T19 (CLI +
    # ConsoleApprover abort signal). Do NOT silently leave this state absent:
    # see PLAN.md "HUMAN_ABORTED wiring (T19)".
    HUMAN_ABORTED = "HUMAN_ABORTED"  # mandated terminal state; see note above

    def __init__(self, llm, config, dispatcher, guardrail, hitl, feedback_engine, context_manager, sandbox=None):
        self.llm = llm
        self.config = config
        self.dispatcher = dispatcher
        self.guardrail = guardrail
        self.hitl = hitl
        self.feedback_engine = feedback_engine
        self.context_manager = context_manager
        self.sandbox = sandbox

    def _snapshot(self, path):
        p = os.path.join(self.config.project_root, path)
        try:
            with open(p) as f:
                return f.read().splitlines(keepends=True)
        except OSError:
            return []

    def run(self, task: Task) -> RunResult:
        before = {}
        for d in self.config.allowed_write_dirs:
            root = os.path.join(self.config.project_root, d)
            if not os.path.isdir(root):
                continue
            for dp, _, fs in os.walk(root):
                for f in fs:
                    rel = os.path.relpath(os.path.join(dp, f), self.config.project_root)
                    before[rel] = self._snapshot(rel)
        ctx = self.context_manager.build_initial(task.test_selector)
        turns, last_fb = [], None
        parse_failures = 0
        for _ in range(self.config.max_iterations):
            raw = self.llm.complete(ctx)
            try:
                action = parse_action(raw)
            except ParseError as e:
                parse_failures += 1
                turns.append(Turn(raw, "ParseError", "Deny", str(e)))
                fb = FailureReport(False, None, [], f"parse error: {e}", "", None, None, "", False)
                ctx = self.context_manager.build(ctx + [Message("assistant", raw)], fb)
                if parse_failures >= self.config.max_parse_failures:
                    return RunResult("ERROR", turns)
                continue
            decision = self.guardrail.check(action)
            summary = ""
            observation = None
            if isinstance(decision, AskHuman):
                decision = self.hitl.request(action, decision.reason)
            # G2: Sandbox — HARD execution-boundary gate. Runs ONLY after the
            # soft guardrail (+HITL) allowed; a Deny here is recorded as a Deny
            # turn below (same as a guardrail Deny) and the action never reaches
            # the dispatcher. Guardrail Deny wins; sandbox is not consulted.
            if self.sandbox is not None and isinstance(decision, Allow):
                sbox = self.sandbox.check(action)
                if isinstance(sbox, Deny):
                    decision = sbox
                elif isinstance(sbox, AskHuman):
                    decision = self.hitl.request(action, sbox.reason)
                elif isinstance(sbox, Containerize):
                    pass  # G5: route to SandboxDockerExecutor instead of the host dispatcher.
                # Allow: fall through unchanged -> proceed to dispatch.
            if isinstance(decision, Allow) and not isinstance(action, Finish):
                # M3: Finish is a TERMINAL control action -- it must NOT be
                # handed to ToolDispatcher (which has no Finish arm and would
                # return the catch-all `unknown action Finish` ToolResult,
                # polluting the turn summary + the §3.10 WebUI stream). Finish
                # falls through to the termination check below.
                result = self.dispatcher.execute(action)
                summary = (result.stdout + result.stderr)[:200]
                if isinstance(action, RunTests):
                    last_fb = self.feedback_engine.classify(result)
                    if last_fb.is_green:
                        turns.append(Turn(raw, type(action).__name__, "Allow", summary))
                        return self._finish("SUCCESS", turns, before)
                    if last_fb.stuck:
                        turns.append(Turn(raw, type(action).__name__, "Allow", summary))
                        return RunResult("STUCK", turns, self._diff(before), last_fb)
                # C2: feed the tool observation back into the next context so
                # the LLM can SEE read_file/list_dir/run_shell/run_tests
                # output. The old loop only stored this in Turn.summary
                # (display), so under a real LLM the agent was blind to its
                # own reads -- mock scripts were observation-independent and
                # masked it. Bounded to the last ~2000 chars for sane growth.
                # (Finish never reaches here: it is excluded above; green/stuck
                # RunTests already returned above.)
                blob = (result.stdout or "") + (result.stderr or "")
                observation = blob[-2000:]
            elif isinstance(decision, Deny):
                summary = f"denied: {decision.reason}"
            turns.append(Turn(raw, type(action).__name__, type(decision).__name__, summary))
            if isinstance(action, Finish):
                return self._finish(
                    "SUCCESS" if (last_fb and last_fb.is_green) else "ERROR", turns, before
                )
            history = ctx + [Message("assistant", raw)]
            if observation is not None:
                history.append(Message("user", "OBSERVATION:\n" + observation))
            ctx = self.context_manager.build(history, last_fb)
        return RunResult("BUDGET_EXHAUSTED", turns, self._diff(before), last_fb)

    def _finish(self, outcome, turns, before):
        return RunResult(outcome, turns, self._diff(before))

    def _diff(self, before):
        out = []
        seen = set()
        for rel, old in before.items():
            seen.add(rel)
            new = self._snapshot(rel)
            if old != new:
                out.extend(difflib.unified_diff(old, new, fromfile=rel, tofile=rel))
        # I4: walk allowed_write_dirs again and emit an "added file" entry for
        # any path created during the run that was NOT in `before`. The old
        # walk iterated only `before.keys()`, so WriteFile of a NEW file
        # produced an empty diff -- breaking US4 observability + §3.10 WebUI.
        for d in self.config.allowed_write_dirs:
            root = os.path.join(self.config.project_root, d)
            if not os.path.isdir(root):
                continue
            for dp, _, fs in os.walk(root):
                for f in fs:
                    rel = os.path.relpath(os.path.join(dp, f), self.config.project_root)
                    if rel in seen:
                        continue
                    seen.add(rel)
                    new = self._snapshot(rel)
                    # Empty `before` for a new file -> diff against nothing,
                    # emitting the whole file as additions (fromfile=/dev/null).
                    out.extend(difflib.unified_diff([], new, fromfile="/dev/null", tofile=rel))
        return "".join(out)
