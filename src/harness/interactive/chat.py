from harness.actions.parser import ParseError, split_prose_and_action
from harness.actions.protocol import EditFile, Finish, RunTests, WriteFile
from harness.governance.diff_preview import DiffPreviewer
from harness.guardrails.guardrail import Allow, AskHuman, Deny
from harness.guardrails.sandbox import Containerize
from harness.interactive.presenter import Presenter
from harness.types import Message


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

    def _agent_loop(self, repo: str, accept: str | None, history: list[Message]) -> str:
        parse_failures = 0
        for _ in range(self.config.max_iterations):
            ctx = self.context_manager.build_chat(repo, accept, history)
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
                        f"your last output had a malformed action ({e.reason}). "
                        "Re-emit ONE action with the correct format per the protocol above.",
                    )
                )
                if parse_failures >= self.config.max_parse_failures:
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
                return "REPLIED"
            decision = self.guardrail.check(action)
            if isinstance(decision, AskHuman):
                # C1: route through the injected HITL (fail-closed in task
                # mode, ConsoleApprover/StubApprover in chat) — NEVER through
                # global input(). Mirrors AgentRunner.run (agent.py:92-93).
                # §3.5 fail-closed: in non-interactive task mode a dangerous /
                # network action is denied rather than hanging on a prompt.
                decision = self.hitl.request(action, decision.reason)
            # G2: Sandbox — HARD execution-boundary gate. Runs ONLY after the
            # soft guardrail (+HITL) allowed, so a guardrail Deny wins and the
            # sandbox is never consulted for an already-denied action. A Deny
            # here is handled identically to a guardrail Deny below.
            if self.sandbox is not None and isinstance(decision, Allow):
                sbox = self.sandbox.check(action)
                if isinstance(sbox, Deny):
                    decision = sbox
                elif isinstance(sbox, AskHuman):
                    decision = self.hitl.request(action, sbox.reason)
                elif isinstance(sbox, Containerize):
                    pass  # G5: route to SandboxDockerExecutor instead of the host dispatcher.
                # Allow: fall through unchanged -> proceed to dispatch.
            if isinstance(decision, Deny):
                self.presenter.show_deny(decision.reason)
                history.append(Message("assistant", raw))
                history.append(
                    Message("user", f"action denied: {decision.reason}; try a different approach.")
                )
                continue
            # G3: DiffPreviewer + approval gate (write-before-apply). Shows the
            # proposed unified diff for Write/Edit and (in "ask" mode) requires
            # approval BEFORE the dispatcher mutates disk. "always" shows then
            # applies; "never" applies silently (and never asks). Runs AFTER the
            # sandbox Allow so a sandbox Deny wins and no preview leaks for a
            # disallowed write. Under a non-interactive approver "ask" is
            # fail-closed: the request returns Deny -> skip.
            if isinstance(action, (WriteFile, EditFile)) and self.config.diff_preview != "never":
                dpath, ddiff = DiffPreviewer.preview(action, self.config.project_root)
                if ddiff:
                    self.presenter.show_diff(dpath, ddiff)
                    if self.config.diff_preview == "ask":
                        verdict = self.hitl.request(action, f"proposed change to {dpath}; approve?")
                        if isinstance(verdict, Deny):
                            self.presenter.show_deny(f"skipped: not approved ({dpath})")
                            history.append(Message("assistant", raw))
                            history.append(
                                Message(
                                    "user",
                                    f"change to {dpath} not approved; try a different approach.",
                                )
                            )
                            continue
            # Fix A: Finish is a TERMINAL signal — handle it BEFORE dispatch.
            # The ToolDispatcher has no Finish case (its catch-all would emit
            # "unknown action Finish"); never dispatch Finish.
            if isinstance(action, Finish):
                self.presenter.show_done(action.reason)
                return "FINISH"
            result = self.dispatcher.execute(action)
            self.presenter.show_action(action, result)
            obs = (result.stdout + "\n" + result.stderr)[-2000:]
            if isinstance(action, RunTests):
                fb = self.feedback_engine.classify(result)
                self.presenter.show_feedback(fb)
                history.append(Message("assistant", raw))
                history.append(
                    Message(
                        "user",
                        "OBSERVATION:\n" + obs + "\nFEEDBACK:\n" + fb.hint + "\n" + fb.traceback_excerpt,
                    )
                )
                if accept and accept in action.args and fb.is_green:
                    self.presenter.show_done(f"acceptance test green: {accept}")
                    return "SUCCESS"
                continue
            history.append(Message("assistant", raw))
            history.append(Message("user", "OBSERVATION:\n" + obs))
        return "BUDGET_EXHAUSTED"

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
            args = cmd[len("/tests"):].strip()
            r = self.dispatcher.execute(RunTests(args))
            self.presenter.show_action(RunTests(args), r)
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
