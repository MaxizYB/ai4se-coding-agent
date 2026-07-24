import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERS = 200_000

class CredentialError(Exception): pass

def _derive(master: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERS)
    return base64.urlsafe_b64encode(kdf.derive(master.encode()))

class CredentialStore:
    def __init__(self, path: str):
        self.path = path

    def _read(self) -> dict:
        if not os.path.exists(self.path):
            return {"salt": base64.b64encode(os.urandom(16)).decode(), "entries": {}}
        with open(self.path) as f:
            return json.loads(f.read())

    def _write(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            f.write(json.dumps(data))
        os.replace(tmp, self.path)

    def set(self, provider: str, key: str, master: str) -> None:
        data = self._read()
        salt = base64.b64decode(data["salt"])
        data["entries"][provider] = Fernet(_derive(master, salt)).encrypt(key.encode()).decode()
        self._write(data)

    def get(self, provider: str, master: str) -> str:
        if not os.path.exists(self.path):
            raise CredentialError("no credential store")
        with open(self.path) as f:
            data = json.loads(f.read())
        if provider not in data.get("entries", {}):
            raise CredentialError(f"no key for {provider}")
        salt = base64.b64decode(data["salt"])
        try:
            return Fernet(_derive(master, salt)).decrypt(data["entries"][provider].encode()).decode()
        except InvalidToken as e:
            raise CredentialError("wrong master password or corrupt store") from e

    def status(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return {p: True for p in json.loads(f.read()).get("entries", {})}

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)
