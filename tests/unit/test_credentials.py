import os

import pytest

from harness.credentials import CredentialError, CredentialStore


def test_roundtrip(tmp_path):
    s = CredentialStore(str(tmp_path / "c.enc"))
    s.set("zhipu", "sk-secret", master="pw123")
    assert s.get("zhipu", "pw123") == "sk-secret"

def test_status_no_plaintext(tmp_path):
    p = str(tmp_path / "c.enc")
    s = CredentialStore(p); s.set("zhipu", "sk-secret", master="pw123")
    with open(p, "rb") as f:
        raw = f.read()
    assert b"sk-secret" not in raw
    assert s.status() == {"zhipu": True}

def test_wrong_master_rejected(tmp_path):
    s = CredentialStore(str(tmp_path / "c.enc")); s.set("zhipu", "k", master="good")
    with pytest.raises(CredentialError):
        s.get("zhipu", "bad")

def test_missing_provider(tmp_path):
    s = CredentialStore(str(tmp_path / "c.enc")); s.set("zhipu", "k", master="good")
    with pytest.raises(CredentialError):
        s.get("openai", "good")

def test_clear(tmp_path):
    p = str(tmp_path / "c.enc"); s = CredentialStore(p); s.set("zhipu", "k", master="g")
    s.clear()
    assert not os.path.exists(p)
