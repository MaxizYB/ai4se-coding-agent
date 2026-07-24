import json
import os

import pytest

import harness.credentials as cred
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


def test_corrupt_store_raises(tmp_path):
    p = str(tmp_path / "c.enc")
    with open(p, "wb") as f:
        f.write(b"\x00\x01 not json \xff\xfe garbage")
    with pytest.raises(CredentialError):
        CredentialStore(p).get("zhipu", "anything")


def test_status_corrupt_returns_empty(tmp_path):
    p = str(tmp_path / "c.enc")
    with open(p, "wb") as f:
        f.write(b"definitely not json")
    assert CredentialStore(p).status() == {}


def test_store_file_mode_owner_only(tmp_path):
    p = str(tmp_path / "c.enc")
    CredentialStore(p).set("zhipu", "sk-secret", master="pw")
    assert os.stat(p).st_mode & 0o777 == 0o600


def test_kdf_iters_persisted_in_header(tmp_path):
    p = str(tmp_path / "c.enc")
    CredentialStore(p).set("zhipu", "sk-secret", master="pw")
    with open(p) as f:
        header = json.loads(f.read())
    assert header["kdf_iters"] == 200_000


def test_get_uses_persisted_kdf_iters(tmp_path, monkeypatch):
    p = str(tmp_path / "c.enc")
    monkeypatch.setattr(cred, "ITERS", 1)
    CredentialStore(p).set("zhipu", "sk-secret", master="pw")
    monkeypatch.setattr(cred, "ITERS", 200_000)
    assert CredentialStore(p).get("zhipu", "pw") == "sk-secret"
