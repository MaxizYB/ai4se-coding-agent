from __future__ import annotations


class TaskReport:
    """Structured end-of-task summary built from the loop's ``task_events`` log.

    A ``task_event`` is a dict the agent loop appends as it executes:
      - ``{"kind": "file_changed", "path": <path>}``  -- after a Write/Edit applies
      - ``{"kind": "shell", "cmd": <cmd>, "ok": <bool>}``  -- after RunShell
      - ``{"kind": "test", "selector": <args>, "green": <bool>}``  -- after RunTests

    ``build`` is a pure, deterministic function -> trivially mock-testable.
    """

    @staticmethod
    def build(task_events: list[dict], outcome: str, agent_summary: str) -> dict:
        files_changed: list[str] = []
        seen: set[str] = set()
        commands_run: list[str] = []
        tests: list[dict] = []
        for ev in task_events:
            kind = ev.get("kind")
            if kind == "file_changed":
                path = ev["path"]
                if path not in seen:
                    seen.add(path)
                    files_changed.append(path)
            elif kind == "shell":
                commands_run.append(ev["cmd"])
            elif kind == "test":
                tests.append({"selector": ev["selector"], "green": ev["green"]})
        return {
            "outcome": outcome,
            "files_changed": files_changed,
            "commands_run": commands_run,
            "tests": tests,
            "summary": agent_summary,
        }
