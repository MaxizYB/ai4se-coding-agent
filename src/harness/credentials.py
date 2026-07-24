import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERS = 200_000


class CredentialError(Exception):
    pass


def _derive(master: str, salt: bytes, iters: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iters)
    return base64.urlsafe_b64encode(kdf.derive(master.encode()))


class CredentialStore:
    def __init__(self, path: str):
        self.path = path

    def _new_header(self) -> dict:
        return {
            "salt": base64.b64encode(os.urandom(16)).decode(),
            "kdf_iters": ITERS,
            "entries": {},
        }

    def _parse_file(self) -> dict:
        with open(self.path, "rb") as f:
            raw = f.read()
        try:
            data = json.loads(raw)
            salt = data["salt"]
            entries = data["entries"]
            iters = data.get("kdf_iters", ITERS)
            base64.b64decode(salt)
            if not isinstance(entries, dict):
                raise CredentialError("corrupt credential store")
            if not isinstance(iters, int) or iters < 1:
                raise CredentialError("corrupt credential store")
            return data
        except (ValueError, KeyError, TypeError) as e:
            raise CredentialError("corrupt credential store") from e

    def _write(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data))
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def set(self, provider: str, key: str, master: str) -> None:
        data = self._parse_file() if os.path.exists(self.path) else self._new_header()
        salt = base64.b64decode(data["salt"])
        iters = data.get("kdf_iters", ITERS)
        data["kdf_iters"] = iters
        fernet = Fernet(_derive(master, salt, iters))
        data["entries"][provider] = fernet.encrypt(key.encode()).decode()
        self._write(data)

    def get(self, provider: str, master: str) -> str:
        if not os.path.exists(self.path):
            raise CredentialError("no credential store")
        data = self._parse_file()
        entries = data["entries"]
        if provider not in entries:
            raise CredentialError(f"no key for {provider}")
        salt = base64.b64decode(data["salt"])
        iters = data.get("kdf_iters", ITERS)
        fernet = Fernet(_derive(master, salt, iters))
        try:
            return fernet.decrypt(entries[provider].encode()).decode()
        except InvalidToken as e:
            raise CredentialError("wrong master password or corrupt store") from e

    def status(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            data = self._parse_file()
        except CredentialError:
            return {}
        return {p: True for p in data["entries"]}

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)
