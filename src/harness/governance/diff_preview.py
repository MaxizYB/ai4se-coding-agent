import difflib
import os

from harness.actions.protocol import Action, EditFile, WriteFile


class DiffPreviewer:
    """Render the unified diff a Write/Edit action WOULD produce before it runs.

    Pure function over the current on-disk content (read once from
    ``project_root/path``); never mutates. Returns ``(path, diff_text)`` where an
    empty ``diff_text`` means the action is a no-op (e.g. EditFile whose ``old``
    substring is absent).
    """

    @staticmethod
    def preview(action: Action, project_root: str) -> tuple[str, str]:
        path = action.path
        before = DiffPreviewer._read(project_root, path)
        if isinstance(action, WriteFile):
            after = action.content
        elif isinstance(action, EditFile):
            after = before.replace(action.old, action.new, 1) if action.old in before else before
        else:
            after = before
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=path,
                tofile=path,
            )
        )
        return path, diff

    @staticmethod
    def _read(project_root: str, path: str) -> str:
        try:
            with open(os.path.join(project_root, path)) as f:
                return f.read()
        except OSError:
            return ""
