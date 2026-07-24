from pathlib import Path
from harness.feedback.pytest_parser import parse_pytest_output
from harness.feedback.types import FailureCategory

FIX = Path(__file__).parent.parent / "fixtures"

def _xml(name): return (FIX / name).read_text()

def test_green_run():
    r = parse_pytest_output(0, "", "", _xml("green.xml"))
    assert r.is_green and r.failed == 0 and r.errors == 0 and r.passed == 2

def test_assertion_failure_parsed():
    r = parse_pytest_output(1, "", "", _xml("assertion.xml"))
    assert not r.is_green and r.failed == 1
    f = r.failures[0]
    assert f.nodeid == "t.Tests.test_add"
    assert f.exc_type == "AssertionError"

def test_import_error_from_collection():
    r = parse_pytest_output(2, "", "", _xml("import_err.xml"))
    assert not r.is_green and r.errors == 1
    assert r.failures[0].exc_type == "ModuleNotFoundError"

def test_no_xml_falls_back_to_stderr():
    r = parse_pytest_output(2, "", "ModuleNotFoundError: No module named 'foo'", "")
    assert not r.is_green and r.failures[0].exc_type == "ModuleNotFoundError"
