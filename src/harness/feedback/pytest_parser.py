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
    # SPEC §3.6: XML missing OR parse-failed (truncated/non-XML from a crashed
    # pytest or OOM mid-write) -> synthesize one pseudo-failure from stderr.
    root = None
    if junit_xml.strip():
        try:
            root = ET.fromstring(junit_xml)
        except ET.ParseError:
            root = None
    if root is None:
        # F5: use the LAST regex match in stderr (the actually-raised exception),
        # not the first, so chained exceptions classify the raised frame.
        matches = _EXC_RE.findall(stderr)
        exc = matches[-1] if matches else "UnknownError"
        msg = stderr.strip().splitlines()[-1] if stderr.strip() else ""
        return TestRunResult(0, 0, 0, 1, [TestFailure("<collection>", exc, msg)], exit_code)
    # Aggregate over every `<testsuite>` regardless of wrapping. pytest's
    # junit_family=xunit2 (the default) emits a `<testsuites>` root whose
    # `tests`/`failures`/`errors` live on the inner `<testsuite>`(s); xunit1
    # emits a bare `<testsuite>` root. `iter` matches the root itself when it is
    # a `<testsuite>`, so both shapes (and multi-suite output) are handled.
    suites = list(root.iter("testsuite"))
    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    passed = total - failed - errors
    failures = []
    for tc in root.iter("testcase"):
        nodeid = _nodeid(tc.get("classname", ""), tc.get("name", ""))
        for tag in ("failure", "error"):
            el = tc.find(tag)
            if el is not None:
                failures.append(TestFailure(nodeid, _infer_exc_type(el),
                                            el.get("message", ""), el.text or ""))
    return TestRunResult(total, max(passed, 0), failed, errors, failures, exit_code)


def _infer_exc_type(el) -> str:
    """C1: real pytest's `<failure>` carries only `message=` (no `type=`), so
    naive `el.get("type", "UnknownError")` made real assertion failures
    classify as UnknownError -> UNKNOWN, collapsing the deep-dim taxonomy on
    the most common case. Prefer an explicit `type=` when present; otherwise
    INFER the exception type from message+text so classification still works.
    """
    explicit = (el.get("type") or "").strip()
    if explicit:
        return explicit
    blob = (el.get("message", "") or "") + "\n" + (el.text or "")
    # Step 1: take the LAST regex match (consistent with the stderr-fallback
    # path) so an explicit raised exception wins over a generic prefix.
    matches = _EXC_RE.findall(blob)
    if matches:
        return matches[-1]
    # Step 2: bare assertion -- pytest's `assert ...` / `E   assert ...` lines.
    for line in blob.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("assert ", "E   assert")):
            return "AssertionError"
    # Step 3: nothing inferable.
    return "UnknownError"
