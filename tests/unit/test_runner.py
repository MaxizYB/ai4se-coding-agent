from harness.tools.runner import TestRunOutput, run_tests


def _make_project(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_t.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n\ndef test_bad():\n    assert 1 + 1 == 3\n")

def test_runner_captures_exit_and_junit(tmp_path):
    _make_project(tmp_path)
    junit = str(tmp_path / "j.xml")
    out = run_tests(["pytest", "--junitxml", junit, "--tb=short", "tests/test_t.py"],
                    str(tmp_path), 30, junit)
    assert isinstance(out, TestRunOutput)
    assert out.exit_code == 1
    assert "<testsuite" in out.junit_xml

def test_runner_timeout(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_slow.py").write_text("import time\ndef test_slow():\n    time.sleep(5)\n")
    junit = str(tmp_path / "j.xml")
    out = run_tests(["pytest", "--junitxml", junit, "tests/test_slow.py"], str(tmp_path), 1, junit)
    assert out.exit_code == 124 and "TimeoutExpired" in out.stderr

def test_runner_honors_source_edit_between_runs(tmp_path):
    # The agent edits source then re-runs within the same second; a .pyc written
    # by the first run can be reused (coarse-mtime collision, e.g. /tmp tmpfs),
    # masking the edit so the loop never observes green. Source must stay authoritative.
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "m.py").write_text("def v():\n    return 1\n")
    (tmp_path / "tests" / "test_m.py").write_text("from m import v\n\ndef test_v():\n    assert v() == 2\n")
    (tmp_path / "conftest.py").write_text(
        "import sys, os\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))\n"
    )
    junit = str(tmp_path / "j.xml")
    cmd = ["pytest", "--junitxml", junit, "--tb=short", "tests/test_m.py"]
    out1 = run_tests(cmd, str(tmp_path), 30, junit)
    assert out1.exit_code == 1  # v()==1 != 2
    (tmp_path / "src" / "m.py").write_text("def v():\n    return 2\n")  # edit -> should pass
    out2 = run_tests(cmd, str(tmp_path), 30, junit)
    assert out2.exit_code == 0  # must reflect edited source, not stale bytecode
