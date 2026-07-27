from harness.actions.protocol import EditFile, WriteFile
from harness.governance.diff_preview import DiffPreviewer


def test_preview_writefile_new_file_is_all_additions(tmp_path):
    # Brand-new file: before is empty, so every content line is an addition.
    action = WriteFile("src/new.py", "line1\nline2\n")
    path, diff = DiffPreviewer.preview(action, str(tmp_path))
    assert path == "src/new.py"
    assert diff != ""  # non-empty for a real change
    assert "--- src/new.py" in diff  # fromfile
    assert "+++ src/new.py" in diff  # tofile
    # No '-' removal lines for a brand-new file (only headers/hunk/additions).
    for line in diff.splitlines():
        if line.startswith(("---", "+++", "@@")):
            continue
        assert line.startswith("+"), f"unexpected non-addition line: {line!r}"
    assert "+line1" in diff and "+line2" in diff


def test_preview_editfile_replacement_emits_minus_plus_hunk(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def f():\n    return 1\n")
    action = EditFile("src/foo.py", "return 1", "return 2")
    path, diff = DiffPreviewer.preview(action, str(tmp_path))
    assert path == "src/foo.py"
    assert "--- src/foo.py" in diff and "+++ src/foo.py" in diff
    assert "-    return 1" in diff
    assert "+    return 2" in diff


def test_preview_editfile_old_not_found_is_empty_noop_diff(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def f():\n    return 1\n")
    action = EditFile("src/foo.py", "nope_not_present", "whatever")
    path, diff = DiffPreviewer.preview(action, str(tmp_path))
    assert path == "src/foo.py"
    assert diff == ""  # old not in current -> after == before -> no-op -> empty diff
