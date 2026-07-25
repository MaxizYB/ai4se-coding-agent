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
