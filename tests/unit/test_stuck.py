from harness.feedback.stuck import StuckDetector, signature_of
from harness.feedback.types import FailureCategory


def test_signature_stable_ignores_order():
    assert signature_of(["a", "b"], FailureCategory.LOGIC) == \
           signature_of(["b", "a"], FailureCategory.LOGIC)

def test_stuck_on_repeated_signature():
    d = StuckDetector(repeat_n=3, no_progress_m=10)
    sig = signature_of(["t.x"], FailureCategory.LOGIC)
    assert d.update(sig, ["t.x"]) is False
    assert d.update(sig, ["t.x"]) is False
    assert d.update(sig, ["t.x"]) is True   # 3rd consecutive repeat

def test_not_stuck_when_changing():
    d = StuckDetector(repeat_n=3, no_progress_m=10)
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is False
    assert d.update(signature_of(["b"], FailureCategory.LOGIC), ["b"]) is False

def test_no_progress_when_failing_set_never_shrinks():
    d = StuckDetector(repeat_n=99, no_progress_m=3)
    d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"])   # largest so far = 1
    d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"])   # no shrink
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is True  # m=3

def test_progress_resets_stuck():
    d = StuckDetector(repeat_n=2, no_progress_m=2)
    d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"])
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is True
    d.reset()
    assert d.update(signature_of(["a"], FailureCategory.LOGIC), ["a"]) is False

def test_shrink_resets_no_progress():
    # Shrinking the failing set is progress -> _no_progress resets to 0, so the
    # detector must NOT declare stuck. repeat_n=3 keeps the repeat branch quiet;
    # no_progress_m=2 means without the reset, call 3 (no_progress==2) would trip.
    d = StuckDetector(repeat_n=3, no_progress_m=2)
    sig_3 = signature_of(["a", "b", "c"], FailureCategory.LOGIC)
    sig_1 = signature_of(["a"], FailureCategory.LOGIC)
    d.update(sig_3, ["a", "b", "c"])   # no_progress=1, _best_failing=3
    d.update(sig_1, ["a"])             # shrink 3->1 resets no_progress=0
    assert d.update(sig_1, ["a"]) is False  # no_progress=1 (<2) -> NOT stuck
