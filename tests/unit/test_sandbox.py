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


def test_edit_inside_write_root_allowed():
    assert isinstance(Sandbox(cfg(sandbox_write_roots=["src"])).check(EditFile("src/x.py", "a", "b")), Allow)


def test_edit_outside_write_roots_denied():
    assert isinstance(Sandbox(cfg(sandbox_write_roots=["src"])).check(EditFile("tests/x.py", "a", "b")), Deny)


# --- denylist (hard deny, short-circuits before network) ---

def test_denylist_rm_rf_root_denied():
    assert isinstance(Sandbox(cfg()).check(RunShell("rm -rf /")), Deny)


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
