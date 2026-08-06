"""Capture ChatRunner presenter callbacks as NDJSON-ready queue events."""
import queue


class WebPresenter:
    def __init__(self, q: queue.Queue | None = None):
        self.q = q or queue.Queue()

    def _emit(self, event_type: str, **data):
        self.q.put({"type": event_type, **data})

    def welcome(self, repo, accept=None):
        self._emit("info", text=f"harness @ {repo}")

    def show_prose(self, text):
        if text:
            self._emit("prose", text=text)

    def show_action(self, action, result):
        name = type(action).__name__
        summary = (result.stdout + result.stderr)[:300].replace("\n", " ")
        path = getattr(action, "path", "")
        self._emit("action", action=name, path=path, summary=summary)

    def show_feedback(self, fb):
        if fb is not None and not fb.is_green:
            self._emit("feedback", category=fb.category.value, hint=fb.hint.strip())

    def show_deny(self, reason):
        self._emit("deny", reason=reason)

    def show_diff(self, path, diff):
        self._emit("diff", path=path, diff=diff[:2000])

    def show_done(self, reason):
        self._emit("done", reason=reason)

    def show_turn_end(self, outcome):
        self._emit("outcome", outcome=outcome)

    def show_info(self, text):
        self._emit("info", text=text)

    def show_report(self, report):
        self._emit("report", **report)

    def ask_human(self, action, reason):
        return False  # web mode = fail-closed

    @property
    def out(self):
        class _Out:
            def __init__(self, q):
                self.q = q

            def write(self, text):
                self.q.put({"type": "raw", "text": text})

        return _Out(self.q)
