from harness.memory.retriever import Retriever


def _write(path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_symbols_collects_function_with_lineno(tmp_path):
    _write(tmp_path / "src" / "foo.py", "def add(a, b):\n    ...\n\nclass Foo:\n    pass\n")
    result = Retriever.symbols(str(tmp_path))
    assert result["add"] == ["src/foo.py:1"]
    assert "Foo" in result
    assert result["Foo"] == ["src/foo.py:4"]


def test_symbols_collects_async_functions(tmp_path):
    _write(tmp_path / "src" / "a.py", "async def runner():\n    return 1\n")
    result = Retriever.symbols(str(tmp_path))
    assert result["runner"] == ["src/a.py:1"]


def test_grep_finds_matching_lines(tmp_path):
    _write(tmp_path / "tests" / "t_x.py", "assert x\n")
    hits = Retriever.grep("assert", str(tmp_path))
    assert hits, "expected at least one hit"
    assert any(h == "tests/t_x.py:1: assert x" for h in hits)


def test_symbols_skips_pycache_and_skip_dirs(tmp_path):
    _write(tmp_path / "src" / "__pycache__" / "x.py", "def pycache_only(a):\n    return a\n")
    _write(tmp_path / "src" / "real.py", "def real_fn(a):\n    return a\n")
    result = Retriever.symbols(str(tmp_path))
    assert "pycache_only" not in result
    assert "real_fn" in result


def test_grep_respects_max_hits(tmp_path):
    _write(tmp_path / "src" / "many.py", "assert one\nassert two\nassert three\n")
    hits = Retriever.grep("assert", str(tmp_path), max_hits=2)
    assert len(hits) == 2


def test_symbols_respects_max_files(tmp_path):
    _write(tmp_path / "src" / "a.py", "def a_fn():\n    ...\n")
    _write(tmp_path / "src" / "b.py", "def b_fn():\n    ...\n")
    _write(tmp_path / "src" / "c.py", "def c_fn():\n    ...\n")
    result = Retriever.symbols(str(tmp_path), max_files=2)
    # only two of the three files contribute symbols (sorted walk -> a, b)
    assert "a_fn" in result and "b_fn" in result
    assert "c_fn" not in result


def test_grep_trims_line_to_cap(tmp_path):
    long_line = "assert " + ("x" * 300)
    _write(tmp_path / "src" / "big.py", long_line + "\n")
    hits = Retriever.grep("assert", str(tmp_path), max_hits=5)
    assert len(hits) == 1
    body = hits[0].split(": ", 1)[1]
    assert len(body) <= 160
