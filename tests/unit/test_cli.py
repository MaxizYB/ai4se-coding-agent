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
