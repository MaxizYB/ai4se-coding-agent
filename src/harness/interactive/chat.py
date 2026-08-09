from harness.actions.parser import ParseError, split_prose_and_action
from harness.actions.protocol import (
    Action,
    EditFile,
    Finish,
    RunShell,
    RunTests,
    WriteFile,
)
from harness.governance.diff_preview import DiffPreviewer
from harness.governance.task_report import TaskReport
from harness.guardrails.guardrail import Allow, AskHuman, Deny, GuardrailDecision
from harness.guardrails.sandbox import Containerize
from harness.interactive.presenter import Presenter
from harness.types import Message

_INTERNAL_USER_PREFIXES = ("OBSERVATION:", "FEEDBACK:", "INTERNAL:")


class ChatRunner:
    def __init__(
        self,
        llm,
        config,
        dispatcher,
        guardrail,
        hitl,
        feedback_engine,
        context_manager,
        presenter=None,
        input_fn=None,
        sandbox=None,
        sandbox_docker=None,
    ):
        self.llm = llm
        self.config = config
        self.dispatcher = dispatcher
        self.guardrail = guardrail
        self.hitl = hitl
        self.feedback_engine = feedback_engine
        self.context_manager = context_manager
        self.presenter = presenter or Presenter()
        self.input_fn = input_fn or input
        self.sandbox = sandbox
        # G5: hard-isolation executor. When the Sandbox returns Containerize and
        # this is injected, RunShell/RunTests run inside a throwaway container
        # (--network=none, read-only fs, repo bind-mounted at /work) instead of
        # the host dispatcher. None (default) => fall back to host dispatch.
        self.sandbox_docker = sandbox_docker
        # G4: per-turn log of tool events (file changes / shell / tests) used to
        # build the structured end-of-task summary. Reset at the start of each
        # `_agent_loop` so the report reflects ONE task, not the whole session.
        self.task_events: list[dict] = []

    def run(self, repo: str, accept: str | None = None) -> int:
        self.presenter.welcome(repo, accept)
        history: list[Message] = []
        while True:
            try:
                line = self.input_fn("> ")
            except (EOFError, KeyboardInterrupt):
                self.presenter.show_done("bye")
                return 0
            if line is None or line.strip() == "":
                continue
            if line.strip().startswith("/"):
                if self._slash(line.strip(), history):
                    return 0
                continue
            history.append(Message("user", line))
            outcome = self._agent_loop(repo, accept, history)
            if outcome != "REPLIED":
                # REPLIED is a normal conversational turn — no status line.
                # SUCCESS/FINISH/BUDGET/ERROR get an explicit end-of-turn marker.
                self.presenter.show_turn_end(outcome)
            if outcome == "SUCCESS":
                # task satisfied; clear the completed turn's tool history, keep chatting
                history = [m for m in history if m.role == "user"][-1:]

    def run_task(self, repo: str, goal: str, accept: str | None = None) -> int:
        self.presenter.welcome(repo, accept)
        history: list[Message] = [Message("user", goal)]
        outcome = self._agent_loop(repo, accept, history)
        self.presenter.show_turn_end(outcome)
        # I1: --accept demands proof. rc 0 requires the accept test to have
        # gone green (outcome == "SUCCESS"); a self-certified Finish (or any
        # non-green terminal state, incl. a plain REPLIED without acting) is
        # rejected. Without this the agent could return success via Finish/REPLY
        # without ever running the accept test.
        if accept and outcome != "SUCCESS":
            self.presenter.show_info(f"acceptance test not verified: {accept}")
            return 1
        return 0 if outcome in ("SUCCESS", "FINISH", "REPLIED") else 1

    def _agent_loop(
        self,
        repo: str,
        accept: str | None,
        history: list[Message],
    ) -> str:
        # G4: reset the per-turn event log so each report covers exactly one task.
        self.task_events = []
        parse_failures = 0
        response_language = self._response_language(history)
        for _ in range(self.config.max_iterations):
            ctx = self.context_manager.build_chat(
                repo,
                accept,
                history,
                response_language=response_language,
            )
            raw = self.llm.complete(ctx)
            try:
                prose, action = split_prose_and_action(raw)
            except ParseError as e:
                parse_failures += 1
                self.presenter.show_deny(f"parse error: {e.reason}")
                history.append(Message("assistant", raw))
                history.append(
                    Message(
                        "user",
                        f"INTERNAL: your last output had a malformed action ({e.reason}). "
                        "Re-emit ONE action with the correct format per the protocol above.",
                    )
                )
                if parse_failures >= self.config.max_parse_failures:
                    self._emit_report("ERROR", "ERROR")
                    return "ERROR"
                continue
            self.presenter.show_prose(prose)
            if action is None:
                # Pure-prose reply (no tool action): END the turn and return
                # control to the user — the Claude/Codex model. The previous
                # `continue` re-prompted the agent internally until it emitted
                # Finish, so the user saw a "done/FINISH" after EVERY message
                # and could not hold a conversation. Plain text = conversational
                # reply or final summary; only a tool ACTION keeps the loop going.
                history.append(Message("assistant", raw))
                # G4: a pure-prose REPLIED turn with NO tool events skips the
                # report (avoids noise on simple Q&A); one that DID act shows it.
                self._emit_report("REPLIED", prose)
                return "REPLIED"
            # G2/G5: soft guardrail (+HITL) then HARD sandbox gate. Shared with
            # the `/tests` slash command via _gate() so neither path can bypass
            # the fence. When the Sandbox says Containerize and an executor is
            # injected, use_docker is set so the dispatch below routes to it
            # (hard isolation). Containerize WITHOUT an executor is fail-closed.
            decision, use_docker = self._gate(action)
            if isinstance(decision, Deny):
                self.presenter.show_deny(decision.reason)
                history.append(Message("assistant", raw))
                history.append(
                    Message("user", f"INTERNAL: action denied: {decision.reason}; try a different approach.")
                )
                continue
            # G3: DiffPreviewer + approval gate (write-before-apply). In "ask"
            # mode the diff is shown ONLY after the approver says yes (#6: do not
            # print a proposed diff for a write that will be denied). "always"
            # shows then applies; "never" applies silently (and never asks). Runs
            # AFTER the sandbox Allow so a sandbox Deny wins and no preview leaks.
            if isinstance(action, (WriteFile, EditFile)) and self.config.diff_preview != "never":
                dpath, ddiff = DiffPreviewer.preview(action, self.config.project_root)
                if ddiff:
                    if self.config.diff_preview == "ask":
                        verdict = self.hitl.request(action, f"proposed change to {dpath}; approve?")
                        if isinstance(verdict, Deny):
                            self.presenter.show_deny(f"skipped: not approved ({dpath})")
                            history.append(Message("assistant", raw))
                            history.append(
                                Message(
                                    "user",
                                    f"INTERNAL: change to {dpath} not approved; try a different approach.",
                                )
                            )
                            continue
                        # approved -> NOW reveal the diff being applied
                        self.presenter.show_diff(dpath, ddiff)
                    else:  # "always": show then auto-apply, no approval step
                        self.presenter.show_diff(dpath, ddiff)
            # Fix A: Finish is a TERMINAL signal — handle it BEFORE dispatch.
            # The ToolDispatcher has no Finish case (its catch-all would emit
            # "unknown action Finish"); never dispatch Finish.
            if isinstance(action, Finish):
                self.presenter.show_done(action.reason)
                self._emit_report("FINISH", action.reason)
                return "FINISH"
            # G5: route a Containerize decision to the SandboxDockerExecutor
            # (throwaway container) when one is injected; otherwise fall back to
            # the host dispatcher so non-containerized runs still work. Only
            # RunShell/RunTests are ever Containerized (see Sandbox.check).
            if use_docker and isinstance(action, RunShell):
                result = self.sandbox_docker.run_shell(action)
            elif use_docker and isinstance(action, RunTests):
                result = self.sandbox_docker.run_tests(action)
            else:
                result = self.dispatcher.execute(action)
            self.presenter.show_action(action, result)
            # G4: record the tool event AFTER it actually applied (post diff-
            # gate, post-dispatch). ReadFile/ListDir are observability-only and
            # intentionally NOT recorded — they change nothing.
            if isinstance(action, (WriteFile, EditFile)):
                self.task_events.append({"kind": "file_changed", "path": action.path})
            elif isinstance(action, RunShell):
                self.task_events.append(
                    {"kind": "shell", "cmd": action.command, "ok": result.ok}
                )
            obs = (result.stdout + "\n" + result.stderr)[-2000:]
            if isinstance(action, RunTests):
                fb = self.feedback_engine.classify(result)
                self.presenter.show_feedback(fb)
                self.task_events.append(
                    {"kind": "test", "selector": action.args, "green": fb.is_green}
                )
                history.append(Message("assistant", raw))
                history.append(
                    Message(
                        "user",
                        "OBSERVATION:\n" + obs + "\nFEEDBACK:\n" + fb.hint + "\n" + fb.traceback_excerpt,
                    )
                )
                if accept and accept in action.args and fb.is_green:
                    self.presenter.show_done(f"acceptance test green: {accept}")
                    self._emit_report("SUCCESS", f"acceptance test green: {accept}")
                    return "SUCCESS"
                continue
            history.append(Message("assistant", raw))
            history.append(Message("user", "OBSERVATION:\n" + obs))
        self._emit_report("BUDGET_EXHAUSTED", "BUDGET_EXHAUSTED")
        return "BUDGET_EXHAUSTED"

    @staticmethod
    def _latest_external_prompt(history: list[Message]) -> str:
        return next(
            (
                item.content.strip().lower()
                for item in reversed(history)
                if item.role == "user"
                and not item.content.lstrip().startswith(_INTERNAL_USER_PREFIXES)
            ),
            "",
        )

    @classmethod
    def _response_language(cls, history: list[Message]) -> str:
        """Choose a deterministic output-language directive for chat prose."""

        prompt = cls._latest_external_prompt(history)
        return "Simplified Chinese" if any("\u3400" <= char <= "\u9fff" for char in prompt) else "English"

    def _emit_report(self, outcome: str, agent_summary: str) -> None:
        # G4: build + render the structured end-of-task summary. A pure-prose
        # REPLIED turn with no tool events is suppressed (no noise on Q&A).
        if outcome == "REPLIED" and not self.task_events:
            return
        report = TaskReport.build(self.task_events, outcome, agent_summary)
        self.presenter.show_report(report)

    def _gate(self, action: Action) -> tuple[GuardrailDecision, bool]:
        """Soft guardrail (+HITL) then HARD sandbox gate. Shared by the agent
        loop and the ``/tests`` slash command so neither path bypasses the fence.

        Returns ``(decision, use_docker)``. C1: AskHuman routes through the
        injected HITL (fail-closed in task mode, never global input()). G5:
        Containerize + an injected executor sets ``use_docker=True``; Containerize
        WITHOUT an executor is FAIL-CLOSED (Deny) — never a silent host fallback,
        which would bypass the requested hard isolation (#5).
        """
        decision = self.guardrail.check(action)
        if isinstance(decision, AskHuman):
            decision = self.hitl.request(action, decision.reason)
        use_docker = False
        if self.sandbox is not None and isinstance(decision, Allow):
            sbox = self.sandbox.check(action)
            if isinstance(sbox, Deny):
                decision = sbox
            elif isinstance(sbox, AskHuman):
                decision = self.hitl.request(action, sbox.reason)
            elif isinstance(sbox, Containerize):
                if self.sandbox_docker is not None:
                    use_docker = True
                else:
                    # #5 fail-closed: hard isolation was requested but no
                    # executor is configured. Deny + surface why; do NOT run on
                    # the host (that would defeat the requested isolation).
                    decision = Deny("containerize requested but no docker executor configured")
            # Allow: fall through unchanged -> proceed to dispatch.
        return decision, use_docker

    def _slash(self, cmd: str, history: list[Message]) -> bool:
        """Return True if the REPL should exit."""
        c = cmd.lower()
        if c in ("/exit", "/quit"):
            self.presenter.show_done("bye")
            return True
        if c == "/clear":
            history.clear()
            self.presenter.show_info("(context cleared)")
            return False
        if c == "/help":
            self.presenter.show_info(
                "commands: /help /exit /clear /tests [selector] /status\n"
                "actions: read_file list_dir write_file edit_file run_shell run_tests finish"
            )
            return False
        if c.startswith("/tests"):
            # #8: route through the SAME guardrail->sandbox gate as the agent
            # loop (via _gate), so containerize/offline/write-root/fail-closed
            # all apply. A Deny is surfaced and the host dispatcher is never
            # reached for a gated-off run_tests.
            args = cmd[len("/tests"):].strip()
            action = RunTests(args)
            decision, use_docker = self._gate(action)
            if isinstance(decision, Deny):
                self.presenter.show_deny(decision.reason)
                return False
            if use_docker:
                r = self.sandbox_docker.run_tests(action)
            else:
                r = self.dispatcher.execute(action)
            self.presenter.show_action(action, r)
            fb = self.feedback_engine.classify(r)
            self.presenter.show_feedback(fb)
            return False
        if c == "/status":
            self.presenter.show_info(
                f"budget max_iterations={self.config.max_iterations}; history={len(history)} msgs"
            )
            return False
        self.presenter.show_info(f"unknown command: {cmd} (/help for list)")
        return False
