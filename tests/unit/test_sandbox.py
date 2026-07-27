import os

from harness.actions.protocol import EditFile, ReadFile, RunShell, RunTests, WriteFile
from harness.config import Config, load_config
from harness.guardrails.sandbox import Allow, AskHuman, Containerize, Deny, Sandbox


def cfg(**kw):
    c = Config.default()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# --- write-root fence ---

def test_write_outside_write_roots_denied():
    d = Sandbox(cfg(sandbox_write_roots=["src"])).check(WriteFile("tests/x.py", "x"))
    assert isinstance(d, Deny)


def test_write_inside_write_root_allowed():
    assert isinstance(Sandbox(cfg(sandbox_write_roots=["src"])).check(WriteFile("src/x.py", "x")), Allow)


# #2: Sandbox is the HARD boundary — it must be at least as strict as the
# Guardrail, which already resolves symlinks via realpath. abspath leaves the
# symlink lexical, so `src/link -> /tmp/outside` smuggles a write out of the
# fence. realpath must resolve the link and Deny.
def test_write_through_symlink_escape_denied(tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (tmp_path / "src").mkdir()
    os.symlink(outside, str(tmp_path / "src" / "link"))
    sb = Sandbox(cfg(project_root=str(tmp_path), sandbox_write_roots=["src"]))
    d = sb.check(WriteFile("src/link/smuggled.py", "x"))
    assert isinstance(d, Deny)


def test_edit_inside_write_root_allowed():
    assert isinstance(Sandbox(cfg(sandbox_write_roots=["src"])).check(EditFile("src/x.py", "a", "b")), Allow)


def test_edit_outside_write_roots_denied():
    assert isinstance(Sandbox(cfg(sandbox_write_roots=["src"])).check(EditFile("tests/x.py", "a", "b")), Deny)


# --- denylist (hard deny, short-circuits before network) ---

def test_denylist_rm_rf_root_denied():
    assert isinstance(Sandbox(cfg()).check(RunShell("rm -rf /")), Deny)


# #3: rm -rf must be denied even WITHOUT a leading "/" target — the old pattern
# (rm\s+-rf\s+/) only matched `rm -rf /`, so `rm -rf src` / `rm -rf .` escaped the
# hard fence. sed -i mutates files in place (bypasses the write-root fence) -> Deny.
def test_denylist_rm_rf_subdir_denied():
    assert isinstance(Sandbox(cfg()).check(RunShell("rm -rf src")), Deny)


def test_denylist_rm_rf_dot_denied():
    assert isinstance(Sandbox(cfg()).check(RunShell("rm -rf .")), Deny)


def test_denylist_sed_inplace_denied():
    assert isinstance(Sandbox(cfg()).check(RunShell("sed -i 's/a/b/' f")), Deny)


# --- network egress modes ---

def test_network_offline_denies_curl():
    assert isinstance(Sandbox(cfg(sandbox_network="offline")).check(RunShell("curl http://x")), Deny)


def test_network_allowlist_empty_asks_curl():
    d = Sandbox(cfg(sandbox_network="allowlist", sandbox_network_allow=[])).check(RunShell("curl http://x"))
    assert isinstance(d, AskHuman)


def test_network_allowlist_with_allowed_curl_permits():
    d = Sandbox(cfg(sandbox_network="allowlist", sandbox_network_allow=["curl"])).check(RunShell("curl http://x"))
    assert isinstance(d, Allow)


def test_network_open_allows_curl():
    assert isinstance(Sandbox(cfg(sandbox_network="open")).check(RunShell("curl http://x")), Allow)


# #4: network-tool matching must use the SAME (strong) approach as the Guardrail
# (version-suffix + \s+), not the old \b{escape}\b which missed pip3/double-space.
# The bare "http" entry is GONE (it false-matched `grep http`); raw URLs are now
# caught via https?:// instead.
def test_network_detects_pip3_install():
    # pip3 carries a version suffix the old \b{escape}\b regex missed.
    d = Sandbox(cfg(sandbox_network="offline")).check(RunShell("pip3 install x"))
    assert isinstance(d, Deny)


def test_network_detects_pip_double_space():
    # \s+ (not a single literal space) must still match `pip  install`.
    d = Sandbox(cfg(sandbox_network="offline")).check(RunShell("pip  install x"))
    assert isinstance(d, Deny)


def test_network_does_not_flag_grep_http():
    # bare "http" false-matched "grep http"; dropped entry must NOT flag it.
    assert isinstance(Sandbox(cfg(sandbox_network="offline")).check(RunShell("grep http src/app.py")), Allow)


def test_network_detects_raw_url():
    # A raw URL with no recognized tool still signals egress (https?://).
    d = Sandbox(cfg(sandbox_network="offline")).check(RunShell("python -c \"u('https://evil.example.com')\""))
    assert isinstance(d, Deny)


# --- containerize gate ---

def test_containerize_shell_returns_containerize():
    assert isinstance(Sandbox(cfg(sandbox_containerize=True)).check(RunShell("ls")), Containerize)


def test_containerize_run_tests_returns_containerize():
    assert isinstance(Sandbox(cfg(sandbox_containerize=True)).check(RunTests("")), Containerize)


def test_safe_shell_allowed_when_not_containerized():
    assert isinstance(Sandbox(cfg(sandbox_containerize=False)).check(RunShell("ls")), Allow)


def test_run_tests_allowed_when_not_containerized():
    assert isinstance(Sandbox(cfg(sandbox_containerize=False)).check(RunTests("")), Allow)


# --- passthrough ---

def test_read_action_passes_through_allowed():
    assert isinstance(Sandbox(cfg()).check(ReadFile("src/x.py")), Allow)


# --- config wiring ---

def test_sandbox_defaults_are_safe():
    c = Config.default()
    assert c.sandbox_network == "allowlist"
    assert c.sandbox_network_allow == []
    assert c.sandbox_denied_commands == [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf",
        r"sed\s+-i",
        r"mkfs",
        r"dd\s+.*\bof=",
        r":\(\)\s*\{",
        r">\s*/dev/sd",
        r"sudo",
    ]
    assert c.sandbox_write_roots == ["src"]
    assert c.sandbox_containerize is False
    assert c.sandbox_container_image == "python:3.11-slim"


def test_load_config_reads_sandbox_section(tmp_path):
    toml = """
[sandbox]
network = "offline"
network_allow = ["curl", "wget"]
denied_commands = ["forbidden-thing"]
write_roots = ["src", "tests"]
containerize = true
container_image = "custom:latest"
"""
    p = tmp_path / "harness.toml"
    p.write_text(toml)
    c = load_config(str(p))
    assert c.sandbox_network == "offline"
    assert c.sandbox_network_allow == ["curl", "wget"]
    assert c.sandbox_denied_commands == ["forbidden-thing"]
    assert c.sandbox_write_roots == ["src", "tests"]
    assert c.sandbox_containerize is True
    assert c.sandbox_container_image == "custom:latest"
