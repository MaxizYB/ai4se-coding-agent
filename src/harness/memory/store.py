import json
import os


class MemoryStore:
    def __init__(self, notes_path: str, log_path: str):
        self.notes_path = notes_path
        self.log_path = log_path

    def load_notes(self) -> str:
        if not os.path.exists(self.notes_path):
            return ""
        with open(self.notes_path) as f:
            return f.read()

    def save_notes(self, text: str) -> None:
        with open(self.notes_path, "w") as f:
            f.write(text)

    def append_log(self, entry: dict) -> None:
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def recent_log(self, n: int) -> list[dict]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path) as f:
            return [json.loads(x) for x in f.read().splitlines()[-n:]]
