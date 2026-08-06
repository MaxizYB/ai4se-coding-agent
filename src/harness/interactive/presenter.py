import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from harness.feedback.types import FailureReport


class Presenter:
    def __init__(self, out=None, err=None):
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self._console = Console(file=self.out, force_terminal=sys.stdout.isatty())

    def welcome(self, repo: str, accept: str | None = None) -> None:
        line = f"harness @ [bold]{repo}[/bold]"
        if accept:
            line += f"  (accept: {accept})"
        line += "  — type your task, [dim]/help[/dim] for commands"
        self._console.print(line)

    def show_prose(self, text: str) -> None:
        if text:
            self._console.print(Text(text, style="cyan"))

    def show_action(self, action, result) -> None:
        name = type(action).__name__
        summary = (result.stdout + result.stderr)[:200].replace("\n", " ")
        self._console.print(f"  [dim]-> {name}:[/dim] {summary}")

    def show_feedback(self, fb: FailureReport) -> None:
        if fb is not None and not fb.is_green:
            self._console.print(
                f"  [yellow]feedback [{fb.category.value}]:[/yellow] {fb.hint.strip()}"
            )

    def show_deny(self, reason: str) -> None:
        self._console.print(f"  [red]denied:[/red] {reason}")

    def show_diff(self, path: str, diff: str) -> None:
        body = diff[:2000]
        self._console.print(
            Panel(body, title=f"proposed change: {path}", border_style="blue", expand=False)
        )

    def show_done(self, reason: str) -> None:
        self._console.print(f"  [green]done:[/green] {reason}")

    def show_turn_end(self, outcome: str) -> None:
        color = "green" if outcome == "SUCCESS" else "yellow"
        self._console.print(f"  [{color}]--- {outcome} ---[/{color}]")

    def show_info(self, text: str) -> None:
        self._console.print(text)

    def show_report(self, report: dict) -> None:
        files = report.get("files_changed") or []
        cmds = report.get("commands_run") or []
        tests = report.get("tests") or []
        lines = [f"[bold]outcome:[/bold] {report.get('outcome', '')}"]
        lines.append(f"[bold]files changed:[/bold] {', '.join(files) if files else '(none)'}")
        lines.append(f"[bold]commands:[/bold] {', '.join(cmds) if cmds else '(none)'}")
        if tests:
            entries = [
                f"{t['selector']}=[green]green[/green]" if t["green"]
                else f"{t['selector']}=[red]red[/red]"
                for t in tests
            ]
            lines.append(f"[bold]tests:[/bold] {', '.join(entries)}")
        else:
            lines.append("[bold]tests:[/bold] (none)")
        lines.append(f"[bold]summary:[/bold] {report.get('summary', '') or '(none)'}")
        self._console.print(Panel("\n".join(lines), title="task report", border_style="cyan", expand=False))

    def _write(self, s: str) -> None:
        self.out.write(s + "\n")
