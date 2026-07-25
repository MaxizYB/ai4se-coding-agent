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
    """Patch AgentRunner→fake returning `outcome`; ZhipuLLMClient→no-op (no network)."""
    class _FakeRunner:
        def __init__(self, *a, **kw):
            pass

        def run(self, task):
            return RunResult(outcome=outcome, edits_diff=edits_diff)

    monkeypatch.setattr("harness.agent.AgentRunner", _FakeRunner)
    monkeypatch.setattr("harness.llm.zhipu.ZhipuLLMClient", lambda *a, **kw: None)


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
