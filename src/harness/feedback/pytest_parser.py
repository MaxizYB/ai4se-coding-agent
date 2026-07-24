import re
import xml.etree.ElementTree as ET

from harness.feedback.types import TestFailure, TestRunResult

# F2: include `Expired` so subprocess.TimeoutExpired in stderr reaches TIMEOUT.
_EXC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Expired)):")

def _nodeid(clsname: str, name: str) -> str:
    # NOTE (F1): junit gives classname (dotted module) + name, NOT pytest's
    # `path::name` selector. We emit `classname.name` as the display nodeid;
    # correlation to Task.test_selector is by TEST-NAME suffix (see Task 7
    # `test_name_of`), since the red-green fixer normally targets one test.
    return f"{clsname}.{name}" if clsname else name

def parse_pytest_output(exit_code: int, stdout: str, stderr: str, junit_xml: str) -> TestRunResult:
    if not junit_xml.strip():
        # F5: use the LAST regex match in stderr (the actually-raised exception),
        # not the first, so chained exceptions classify the raised frame.
        matches = _EXC_RE.findall(stderr)
        exc = matches[-1] if matches else "UnknownError"
        msg = stderr.strip().splitlines()[-1] if stderr.strip() else ""
        return TestRunResult(0, 0, 0, 1, [TestFailure("<collection>", exc, msg)], exit_code)
    root = ET.fromstring(junit_xml)
    total = int(root.get("tests", 0)); failed = int(root.get("failures", 0))
    errors = int(root.get("errors", 0)); passed = total - failed - errors
    failures = []
    for tc in root.findall("testcase"):
        nodeid = _nodeid(tc.get("classname", ""), tc.get("name", ""))
        for tag in ("failure", "error"):
            el = tc.find(tag)
            if el is not None:
                failures.append(TestFailure(nodeid, el.get("type", "UnknownError"),
                                            el.get("message", ""), el.text or ""))
    return TestRunResult(total, max(passed, 0), failed, errors, failures, exit_code)
