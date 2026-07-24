from harness.actions.protocol import ReadFile, RunShell, RunTests, WriteFile
from harness.config import Config
from harness.guardrails.guardrail import Allow, AskHuman, Deny, Guardrail


def cfg(patterns=None, net=None, allowed=None):
    c = Config.default()
    c.dangerous_shell_patterns = patterns or [r"rm\s+-rf?"]
    c.network_commands = net or ["pip install", "curl"]
    if allowed: c.allowed_write_dirs = allowed
    return c


def test_read_allowed_in_scope():
    assert isinstance(Guardrail(cfg()).check(ReadFile("src/a.py")), Allow)


def test_write_out_of_scope_denied():
    d = Guardrail(cfg(allowed=["src"])).check(WriteFile("tests/t.py", "x"))
    assert isinstance(d, Deny)


def test_write_in_scope_allowed():
    assert isinstance(Guardrail(cfg(allowed=["src"])).check(WriteFile("src/a.py", "x")), Allow)


def test_dangerous_shell_asks_human():
    assert isinstance(Guardrail(cfg()).check(RunShell("rm -rf build")), AskHuman)


def test_network_command_asks_human():
    assert isinstance(Guardrail(cfg()).check(RunShell("pip install foo")), AskHuman)


def test_network_command_variant_asks_human():
    # Regression: `(" " + net) in cmd` missed `pip3 install` (false-negative,
    # fail-unsafe). Word-boundary match must catch the pip3 variant.
    assert isinstance(Guardrail(cfg()).check(RunShell("pip3 install evil")), AskHuman)


def test_safe_shell_allowed():
    assert isinstance(Guardrail(cfg()).check(RunShell("ls")), Allow)


def test_run_tests_allowed():
    assert isinstance(Guardrail(cfg()).check(RunTests("")), Allow)


def test_write_path_traversal_denied():
    # Security crux: abspath escapes project_root -> must Deny regardless of
    # allowed_write_dirs (exercises the ap.startswith(root+os.sep) fence).
    d = Guardrail(cfg(allowed=["src"])).check(WriteFile("../../etc/passwd", "x"))
    assert isinstance(d, Deny)


def test_edit_path_traversal_denied():
    from harness.actions.protocol import EditFile
    d = Guardrail(cfg(allowed=["src"])).check(EditFile("../outside.py", "a", "b"))
    assert isinstance(d, Deny)


def test_write_through_symlink_to_outside_denied(tmp_path):
    # Regression: lexical abspath lets a symlinked `src -> /tmp/outside` smuggle
    # writes out of scope. realpath must resolve the link and Deny.
    import os

    (tmp_path / "src").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "src" / "link"
    os.symlink(outside, link)
    c = Config.default()
    c.project_root = str(tmp_path)
    c.allowed_write_dirs = ["src"]
    d = Guardrail(c).check(WriteFile("src/link/smuggled.py", "x"))
    assert isinstance(d, Deny)


def test_unknown_action_subtype_is_denied():
    # Security boundary must fail closed: an unrecognized Action subtype that
    # is neither read/write/shell/test must NOT silently Allow.
    from harness.actions.protocol import Action

    class MysteryAction(Action):
        pass

    d = Guardrail(cfg()).check(MysteryAction())
    assert isinstance(d, Deny)


def test_finish_action_allowed():
    from harness.actions.protocol import Finish
    assert isinstance(Guardrail(cfg()).check(Finish("done")), Allow)
