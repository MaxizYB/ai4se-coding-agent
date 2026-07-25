from harness.actions.parser import ParseError, split_prose_and_action
from harness.actions.protocol import Finish, RunTests
from harness.guardrails.guardrail import Allow, AskHuman, Deny
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
            self.presenter.show_turn_end(outcome)
            if outcome == "SUCCESS":
                # task satisfied; clear the completed turn's tool history, keep chatting
                history = [m for m in history if m.role == "user"][-1:]

    def run_task(self, repo: str, goal: str, accept: str | None = None) -> int:
        self.presenter.welcome(repo, accept)
        history: list[Message] = [Message("user", goal)]
        outcome = self._agent_loop(repo, accept, history)
        self.presenter.show_turn_end(outcome)
        return 0 if outcome in ("SUCCESS", "FINISH") else 1

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
                        f"your last output was not a valid action: {e.reason}; emit one ACTION per turn.",
                    )
                )
                if parse_failures >= self.config.max_parse_failures:
                    return "ERROR"
                continue
            self.presenter.show_prose(prose)
            if action is None:
                history.append(Message("assistant", raw))
                continue  # pure narration; let the agent continue
            decision = self.guardrail.check(action)
            if isinstance(decision, AskHuman):
                decision = (
                    Allow() if self.presenter.ask_human(action, decision.reason) else Deny("human denied")
                )
            if isinstance(decision, Deny):
                self.presenter.show_deny(decision.reason)
                history.append(Message("assistant", raw))
                history.append(
                    Message("user", f"action denied: {decision.reason}; try a different approach.")
                )
                continue
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
            if isinstance(action, Finish):
                self.presenter.show_done(action.reason)
                return "FINISH"
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
