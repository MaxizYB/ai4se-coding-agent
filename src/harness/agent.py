import difflib
import os
from dataclasses import dataclass, field

from harness.actions.parser import ParseError, parse_action
from harness.actions.protocol import Finish, RunTests
from harness.feedback.types import FailureReport
from harness.guardrails.guardrail import Allow, AskHuman, Deny
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
    def __init__(self, llm, config, dispatcher, guardrail, hitl, feedback_engine, context_manager):
        self.llm = llm
        self.config = config
        self.dispatcher = dispatcher
        self.guardrail = guardrail
        self.hitl = hitl
        self.feedback_engine = feedback_engine
        self.context_manager = context_manager

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
            if isinstance(decision, AskHuman):
                decision = self.hitl.request(action, decision.reason)
            if isinstance(decision, Allow):
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
            elif isinstance(decision, Deny):
                summary = f"denied: {decision.reason}"
            turns.append(Turn(raw, type(action).__name__, type(decision).__name__, summary))
            if isinstance(action, Finish):
                return self._finish(
                    "SUCCESS" if (last_fb and last_fb.is_green) else "ERROR", turns, before
                )
            ctx = self.context_manager.build(ctx + [Message("assistant", raw)], last_fb)
        return RunResult("BUDGET_EXHAUSTED", turns, self._diff(before), last_fb)

    def _finish(self, outcome, turns, before):
        return RunResult(outcome, turns, self._diff(before))

    def _diff(self, before):
        out = []
        for rel, old in before.items():
            new = self._snapshot(rel)
            if old != new:
                out.extend(difflib.unified_diff(old, new, fromfile=rel, tofile=rel))
        return "".join(out)
