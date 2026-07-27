from harness.agent import RunResult
from harness.cli import main


def test_key_status_empty(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "zhipu" not in out  # nothing set yet


def test_init_then_status(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    prompts = iter(["pw", "sk-KEY"])
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: next(prompts))
    # §3.1: init must capture the API key via getpass (hidden), never input (echoed).
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("input used for secret")))
    assert main(["init"]) == 0
    assert main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "zhipu" in out and "sk-KEY" not in out  # status, no plaintext


def _wire_fix_fake(monkeypatch, outcome, edits_diff=""):
    """Patch AgentRunner→fake returning `outcome`; ZhipuLLMClient→sentinel (no network).

    I2: `_cmd_fix` now decides proceed/abort via `_resolve_llm() is None`, so the
    ZhipuLLMClient stub must return a non-None sentinel (previously None, which
    would now misread as "no credentials" → rc 2). The fake runner ignores llm.
    """
    class _FakeRunner:
        def __init__(self, *a, **kw):
            pass

        def run(self, task):
            return RunResult(outcome=outcome, edits_diff=edits_diff)

    monkeypatch.setattr("harness.agent.AgentRunner", _FakeRunner)
    monkeypatch.setattr("harness.llm.zhipu.ZhipuLLMClient", lambda *a, **kw: ("fake-llm",))


def test_fix_success_prints_outcome_and_diff_returns_0(capsys, tmp_path, monkeypatch):
    # Guards the creds→ZhipuLLMClient→AgentRunner→print wiring + return-code contract.
    monkeypatch.setenv("HOME", str(tmp_path))           # empty credential store
    monkeypatch.setenv("HARNESS_MASTER_PASSWORD", "pw")  # avoids interactive getpass
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")       # env fallback after empty store
    _wire_fix_fake(monkeypatch, outcome="SUCCESS", edits_diff="@@ edits diff here @@")

    rc = main(["fix", "--repo", str(tmp_path), "--test", "x::t"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "OUTCOME: SUCCESS" in out
    assert "@@ edits diff here @@" in out


def test_fix_non_success_returns_1(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HARNESS_MASTER_PASSWORD", "pw")
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")
    _wire_fix_fake(monkeypatch, outcome="STUCK", edits_diff="")

    rc = main(["fix", "--repo", str(tmp_path), "--test", "x::t"])

    assert rc == 1


def test_fix_no_credentials_returns_2(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))             # no credential store
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)    # no env key
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: "dummy")  # no prompt hang

    rc = main(["fix", "--repo", str(tmp_path), "--test", "x::t"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "no credentials" in err


def test_resolve_llm_getpass_eof_falls_through_to_env(tmp_path, monkeypatch):
    # I3: a creds file existing but no TTY / piped stdin (getpass raises
    # EOFError) must NOT crash — it falls through to the ZHIPU_API_KEY env
    # branch. Containers / CI hit this whenever a store exists but no master
    # password is provided.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    cred_path = tmp_path / ".harness" / "credentials.enc"
    cred_path.parent.mkdir(parents=True)
    cred_path.write_bytes(b"x")  # store file exists → enter the getpass branch
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: (_ for _ in ()).throw(EOFError()))
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-env-fallback")
    monkeypatch.setattr("harness.llm.zhipu.ZhipuLLMClient", lambda model, key: ("llm", model, key))

    from harness.cli import _resolve_llm

    assert _resolve_llm() == ("llm", "glm-4.6", "sk-env-fallback")


# #1: `harness task`/`harness fix` under the DEFAULT config (diff_preview="ask")
# must still APPLY a WriteFile. Batch mode wires FailClosedApprover, so an
# un-forced "ask" would deny every write and the agent loops until budget is
# exhausted without mutating. The CLI forces diff_preview="never" in batch mode
# (no human present to approve). Chat stays interactive and honors the config.
def test_task_applies_write_under_default_config(tmp_path, monkeypatch):
    from harness.llm.mock import MockLLMClient

    monkeypatch.setenv("HOME", str(tmp_path))            # no credential store
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-fake")        # env fallback
    monkeypatch.delenv("HARNESS_MASTER_PASSWORD", raising=False)
    (tmp_path / "src").mkdir()
    script = [
        "Writing.\nACTION: write_file\nPATH: src/written.py\n<<<\ndef g():\n    return 1\n>>>\n",
        "ACTION: finish\nREASON: done\n",
    ]
    monkeypatch.setattr("harness.llm.zhipu.ZhipuLLMClient", lambda *a, **kw: MockLLMClient(script))

    rc = main(["task", "--repo", str(tmp_path), "--goal", "write a file"])

    assert rc == 0
    written = tmp_path / "src" / "written.py"
    assert written.exists(), "batch WriteFile must APPLY under default config"
    assert "return 1" in written.read_text()
