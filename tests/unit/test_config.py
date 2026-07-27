import os
import tempfile

from harness.config import Config, load_config


def test_defaults_are_safe():
    c = Config.default()
    assert c.allowed_write_dirs == ["src"]
    assert c.fail_closed_when_noninteractive is True
    assert c.max_iterations == 20 and c.test_timeout_s == 30
    assert c.max_history == 8
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
