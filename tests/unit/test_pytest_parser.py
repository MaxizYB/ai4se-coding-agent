from pathlib import Path

from harness.feedback.classifier import classify_run
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

def test_malformed_xml_falls_back_to_stderr():
    # SPEC §3.6: truncated/non-XML junit (crashed pytest, OOM mid-write) must
    # not raise; fall through to the SAME stderr-fallback path as empty XML.
    r = parse_pytest_output(2, "", "RuntimeError: boom", "<testsuite><testcase")
    assert not r.is_green and r.errors == 1
    assert r.failures[0].exc_type == "RuntimeError"  # synthesized from stderr

def test_wrapped_testsuites_format():
    # Real pytest (xunit2 / junit_family=default) wraps `<testsuite>` inside a
    # `<testsuites>` root. The parser MUST read totals/testcases from the inner
    # suite(s), not the wrapper (which carries no tests/failures attrs). Caught
    # by Task 17's real-pytest integration -- the unwrapped fixtures above hid it.
    r = parse_pytest_output(1, "", "", _xml("wrapped_assertion.xml"))
    assert not r.is_green and r.failed == 1 and r.total == 1
    assert r.failures[0].nodeid == "tests.test_foo.test_add"
    # I3: guard the classification path against real pytest output (xunit2),
    # not just totals. After C1 this classifies LOGIC, not UNKNOWN.
    assert r.failures[0].exc_type == "AssertionError"
    assert classify_run(r) is FailureCategory.LOGIC


def test_real_failure_without_type_attr_infers_assertion_logic():
    # C1 regression: real pytest's `<failure>` carries only `message=` (NO
    # `type=`). Hand-crafted fixtures used `type="AssertionError"` and masked
    # the fact that real assertion failures classified as UnknownError -> UNKNOWN,
    # collapsing the deep-dim taxonomy on the most common case. The fix infers
    # exc_type from the message/text. This uses the REAL captured fixture
    # (Bug-A) whose `<failure>` has no `type=` attribute.
    r = parse_pytest_output(1, "", "", _xml("wrapped_assertion.xml"))
    assert r.failures[0].exc_type == "AssertionError"  # inferred, not "UnknownError"
    assert classify_run(r) is FailureCategory.LOGIC


def test_inferred_exc_uses_last_regex_match_for_chained_exceptions():
    # C1 step 1: when `type=` is absent, apply _EXC_RE and take the LAST match
    # (consistent with the stderr-fallback path) so an explicit exception like
    # subprocess.TimeoutExpired wins over a generic prefix.
    xml = (
        '<testsuite tests="1" failures="1" errors="0">'
        '<testcase classname="t" name="test_x">'
        '<failure message="boom">'
        "ValueError: bad\nsubprocess.TimeoutExpired: cmd 30s"
        "</failure></testcase></testsuite>"
    )
    r = parse_pytest_output(1, "", "", xml)
    assert r.failures[0].exc_type == "subprocess.TimeoutExpired"


def test_inferred_exc_unknown_when_message_has_no_exception():
    # C1 step 3: nothing to infer -> UnknownError (still classified, not a crash).
    xml = (
        '<testsuite tests="1" failures="1" errors="0">'
        '<testcase classname="t" name="test_x">'
        "<failure message='just a message'>no exc here</failure>"
        "</testcase></testsuite>"
    )
    r = parse_pytest_output(1, "", "", xml)
    assert r.failures[0].exc_type == "UnknownError"
