from harness.actions.protocol import EditFile, ListDir, ReadFile, RunShell, WriteFile
from harness.config import Config
from harness.tools.dispatcher import ToolDispatcher


def test_read_file(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("hi")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ReadFile("src/a.py"))
    assert r.ok and r.stdout == "hi"

def test_write_then_edit(tmp_path):
    (tmp_path / "src").mkdir()
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    assert d.execute(WriteFile("src/a.py", "old\n")).ok
    r = d.execute(EditFile("src/a.py", "old", "new"))
    with open(tmp_path / "src" / "a.py") as f:
        assert r.ok and f.read() == "new\n"

def test_edit_old_not_found(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(EditFile("src/a.py", "nope", "new"))
    assert r.ok is False and "not found" in r.stderr.lower()

def test_list_dir(tmp_path):
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x")
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(ListDir("src"))
    assert r.ok and "a.py" in r.stdout

def test_run_shell(tmp_path):
    d = ToolDispatcher(Config.default()); d.config.project_root = str(tmp_path)
    r = d.execute(RunShell("echo hello"))
    assert r.ok and "hello" in r.stdout
