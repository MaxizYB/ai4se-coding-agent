import pytest

from harness.actions.parser import ParseError, parse_action
from harness.actions.protocol import (
    EditFile,
    Finish,
    ReadFile,
    RunShell,
    RunTests,
    WriteFile,
)


def test_parse_simple_param_action():
    a = parse_action("sure, here:\nACTION: read_file\nPATH: src/foo.py\n")
    assert a == ReadFile("src/foo.py")


def test_parse_write_file_with_content_block():
    raw = "ACTION: write_file\nPATH: a.py\n<<<\ndef f():\n    return 1\n>>>\n"
    assert parse_action(raw) == WriteFile("a.py", "def f():\n    return 1\n")


def test_parse_edit_file_old_new_blocks():
    raw = (
        "ACTION: edit_file\nPATH: a.py\n<<<OLD\n    return 1\n>>>OLD\n"
        "<<<NEW\n    return 2\n>>>NEW\n"
    )
    assert parse_action(raw) == EditFile("a.py", "    return 1\n", "    return 2\n")


def test_parse_run_tests_and_shell_and_finish():
    assert parse_action("ACTION: run_tests\nARGS: t.py::test_a\n") == RunTests("t.py::test_a")
    assert parse_action("ACTION: run_tests\n") == RunTests("")
    assert parse_action("ACTION: run_shell\nCOMMAND: pip list\n") == RunShell("pip list")
    assert parse_action("ACTION: finish\nREASON: green\n") == Finish("green")


def test_tolerates_surrounding_prose():
    a = parse_action("Let me read it.\nACTION: read_file\nPATH: x.py\nNow I'll act.")
    assert a == ReadFile("x.py")


def test_parse_error_on_missing_action():
    with pytest.raises(ParseError):
        parse_action("no action here at all")


def test_parse_error_on_unterminated_block():
    with pytest.raises(ParseError):
        parse_action("ACTION: write_file\nPATH: a.py\n<<<\nnever closed")


def test_parse_error_on_missing_path_write_file():
    with pytest.raises(ParseError) as ei:
        parse_action("ACTION: write_file\n<<<\nx\n>>>\n")
    assert ei.value.reason


def test_write_file_block_at_eof_without_trailing_newline():
    # I5: real LLMs often emit the final block at EOF with NO trailing newline
    # after `>>>TAG`. The old `_BLOCK` regex required `\n` there, so the block
    # never matched -> false ParseError. Mock scripts always ended `\n` so the
    # bug was masked; live GLM will omit it. Make the trailing newline optional.
    raw = "ACTION: write_file\nPATH: a.py\n<<<\ndef f():\n    return 1\n>>>"  # no \n
    assert parse_action(raw) == WriteFile("a.py", "def f():\n    return 1\n")


def test_edit_file_blocks_at_eof_without_trailing_newline():
    # I5: same for edit_file's final `>>>NEW` at EOF.
    raw = (
        "ACTION: edit_file\nPATH: a.py\n<<<OLD\n    return 1\n>>>OLD\n"
        "<<<NEW\n    return 2\n>>>NEW"  # no trailing \n
    )
    assert parse_action(raw) == EditFile("a.py", "    return 1\n", "    return 2\n")
