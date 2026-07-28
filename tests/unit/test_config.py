import os
import tempfile

from harness.config import Config, load_config


def test_defaults_are_safe():
    c = Config.default()
    assert c.allowed_write_dirs == ["src"]
    assert c.fail_closed_when_noninteractive is True
    assert c.max_iterations == 20 and c.test_timeout_s == 30
    assert c.max_history == 8
    assert c.context_compact_threshold == 6000  # M1 compactor defaults
    assert c.context_keep_recent == 6
    assert c.diff_preview == "ask"  # G3: default ask (fail-closed in batch)


def test_load_none_returns_defaults():
    assert load_config(None) == Config.default()


def test_load_toml_overrides():
    toml = """
[scope]
allowed_write_dirs = ["src", "lib"]
[budget]
max_iterations = 5
test_timeout_s = 10
[context]
max_history = 4
keep_recent = 2
"""
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as p:
        p.write(toml)
    c = load_config(p.name)
    os.unlink(p.name)
    assert c.allowed_write_dirs == ["src", "lib"]
    assert c.max_iterations == 5 and c.test_timeout_s == 10
    assert c.max_history == 4  # [context] section honored (was silently ignored)
    assert c.fail_closed_when_noninteractive is True  # untouched keeps default


def test_load_governance_diff_preview():
    toml = """
[governance]
diff_preview = "never"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as p:
        p.write(toml)
    c = load_config(p.name)
    os.unlink(p.name)
    assert c.diff_preview == "never"  # [governance] section honored


def test_load_context_compactor_overrides():
    toml = """
[context]
compact_threshold = 1234
keep_recent = 3
"""
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as p:
        p.write(toml)
    c = load_config(p.name)
    os.unlink(p.name)
    assert c.context_compact_threshold == 1234
    assert c.context_keep_recent == 3


def test_load_rejects_keep_recent_plus_one_exceeding_max_history():
    # I1 guard: keep_recent+1 (the compacted summary slot) must fit inside
    # max_history, else the summary is silently dropped by the history bound.
    import pytest

    toml = """
[context]
max_history = 4
keep_recent = 6
"""
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as p:
        p.write(toml)
    try:
        with pytest.raises(ValueError):
            load_config(p.name)
    finally:
        os.unlink(p.name)
