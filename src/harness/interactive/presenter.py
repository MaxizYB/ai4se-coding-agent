import sys

from harness.feedback.types import FailureReport


class Presenter:
    def __init__(self, out=None, err=None):
        self.out = out or sys.stdout
        self.err = err or sys.stderr

    def welcome(self, repo: str, accept: str | None = None) -> None:
        line = f"harness @ {repo}"
        if accept:
            line += f"  (accept: {accept})"
        self._write(f"{line}  — type your task, /help for commands")

    def show_prose(self, text: str) -> None:
        if text:
            self._write(text)

    def show_action(self, action, result) -> None:
        name = type(action).__name__
        summary = (result.stdout + result.stderr)[:200].replace("\n", " ")
        self._write(f"  -> {name}: {summary}")

    def show_feedback(self, fb: FailureReport) -> None:
        if fb is not None and not fb.is_green:
            self._write(f"  feedback [{fb.category.value}]: {fb.hint.strip()}")

    def show_deny(self, reason: str) -> None:
        self._write(f"  denied: {reason}")

    def ask_human(self, action, reason: str) -> bool:
        ans = input(f"  APPROVE {type(action).__name__}? {reason} [y/N]: ")
        return ans.strip().lower() == "y"

    def show_done(self, reason: str) -> None:
        self._write(f"  done: {reason}")

    def show_turn_end(self, outcome: str) -> None:
        self._write(f"  --- {outcome} ---")

    def show_info(self, text: str) -> None:
        self._write(text)

    def _write(self, s: str) -> None:
        self.out.write(s + "\n")
