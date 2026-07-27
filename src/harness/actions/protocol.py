from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    pass


@dataclass(frozen=True)
class ReadFile(Action):
    path: str


@dataclass(frozen=True)
class ListDir(Action):
    path: str


@dataclass(frozen=True)
class WriteFile(Action):
    path: str
    content: str


@dataclass(frozen=True)
class EditFile(Action):
    path: str
    old: str
    new: str


@dataclass(frozen=True)
class RunShell(Action):
    command: str
    stdin: str = ""  # optional stdin to pipe into the command (drive interactive CLIs)


@dataclass(frozen=True)
class RunTests(Action):
    args: str = ""


@dataclass(frozen=True)
class Finish(Action):
    reason: str
