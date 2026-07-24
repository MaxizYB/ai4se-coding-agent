from harness.actions.protocol import (
    Action,
    EditFile,
    Finish,
    ListDir,
    ReadFile,
    RunShell,
    RunTests,
    WriteFile,
)


def test_actions_are_frozen_and_tagged():
    assert isinstance(ReadFile("a.py"), Action)
    assert isinstance(RunTests("tests/test_x.py::test_t"), Action)
    assert isinstance(Finish("done"), Action)

def test_equality_and_fields():
    assert EditFile("a.py", "old", "new") == EditFile("a.py", "old", "new")
    assert WriteFile("a.py", "x").content == "x"
    assert RunShell("ls").command == "ls"
    assert ListDir(".").path == "."
