from harness.cli import main


def test_key_status_empty(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "zhipu" not in out  # nothing set yet

def test_init_then_status(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("getpass.getpass", lambda *_: "pw")
    monkeypatch.setattr("builtins.input", lambda *_: "sk-KEY")
    assert main(["init"]) == 0
    assert main(["key", "status"]) == 0
    out = capsys.readouterr().out
    assert "zhipu" in out and "sk-KEY" not in out  # status, no plaintext
