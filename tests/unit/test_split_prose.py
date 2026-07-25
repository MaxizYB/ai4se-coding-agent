from harness.actions.parser import split_prose_and_action
from harness.actions.protocol import Finish, ReadFile


def test_prose_then_action():
    prose, action = split_prose_and_action("Let me read it.\nACTION: read_file\nPATH: x.py\n")
    assert prose == "Let me read it."
    assert action == ReadFile("x.py")

def test_pure_prose_no_action():
    prose, action = split_prose_and_action("Just thinking, no action this turn.")
    assert prose == "Just thinking, no action this turn."
    assert action is None

def test_action_only_no_prose():
    prose, action = split_prose_and_action("ACTION: finish\nREASON: done\n")
    assert prose == "" and action == Finish("done")

def test_multiline_prose():
    prose, action = split_prose_and_action("line one\nline two\nACTION: finish\nREASON: ok\n")
    assert prose == "line one\nline two" and action == Finish("ok")
