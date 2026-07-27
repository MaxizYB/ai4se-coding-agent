# Memory/Context Deep-Dim Implementation Plan (Compaction + Memory + @mention + Retrieval)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Make memory/context the third deep dimension — long conversations don't blow the context window (compaction), the agent remembers the project (AGENTS.md auto-load), can pull files on-demand (`@mention`), and locate symbols (self-implemented retrieval). All self-implemented (§A.4-D), deterministic, mock-testable.

**Architecture:** `Compactor` (structured — no LLM) trims old turns into a fact-line system message; `ContextManager.build_chat` loads AGENTS.md + resolves `@path` mentions; `Retriever` (stdlib ast/re) provides symbol + grep lookup. Kernel loops unchanged beyond build_chat.

**Tech Stack:** Python ≥3.11 stdlib (`ast`, `re`, `os`, `difflib`).

## Global Constraints
- §A.4-B/C: deterministic, no network/LLM in default tests. §A.4-D: memory storage+retrieval self-implemented (no framework).
- TDD red→green→commit; `ruff check src tests scripts web` clean; `pytest -m "not live" -W error` green/pristine. Existing 199 stay green.
- `chat.py` is primary; `build_chat` is the main integration point.

---

## Task M1: `Compactor` (conversation compaction)

**Files:** Create `src/harness/memory/compactor.py`; modify `src/harness/config.py` (`context_compact_threshold: int = 6000`, `context_keep_recent: int = 6`), `src/harness/context/manager.py` (`build_chat` calls `Compactor.maybe_compact(history)` before assembling). Test `tests/unit/test_compactor.py`.

**Interfaces:**
- `Compactor(config).maybe_compact(history: list[Message]) -> list[Message]`:
  - Estimate size = sum of `len(m.content)` over history.
  - If size <= `config.context_compact_threshold`: return history unchanged.
  - Else: keep `history[-config.context_keep_recent:]`; for each earlier message, produce a one-line fact (structured, NO LLM): if content has `ACTION: <name>` → `"<role>: <action> <key params>"`; elif starts with `OBSERVATION:`/`FEEDBACK:` → first 80 chars; else first 80 chars. Join into one `Message("system", "[compacted history]\n" + "\n".join(facts))`. Return `[that system msg] + history[-keep_recent:]`.
- Pure function (deterministic).

**Tests:** under-threshold → unchanged (same list); over-threshold → 1 system "[compacted...]" + last K; the compacted facts reference the dropped turns' actions; threshold boundary.

- [ ] TDD → `feat(memory): Compactor — structured conversation compaction`.

---

## Task M2: project memory (AGENTS.md auto-load)

**Files:** Modify `src/harness/context/manager.py` (`build_chat` loads `<repo>/AGENTS.md` in addition to HARNESS.md notes; dedupe/merge). Test `tests/unit/test_build_chat.py` (extend).

**Interfaces:** in `build_chat`, after notes: `agents_md = read <repo>/AGENTS.md if exists`; if non-empty, append `Message("system", "Project memory (AGENTS.md):\n" + agents_md)`. (Reuse `MemoryStore` or direct file read.)

**Tests:** AGENTS.md present → its content in a system message; absent → no such message; both AGENTS.md + HARNESS.md → both present.

- [ ] TDD → `feat(memory): auto-load AGENTS.md project memory`.

---

## Task M3: `@mention` file pull

**Files:** Modify `src/harness/context/manager.py` (`build_chat` resolves `@<path>` in the latest user message). Test `tests/unit/test_build_chat.py` (extend) + `tests/integration/test_chat_runner.py`.

**Interfaces:** in `build_chat`, scan the last user message for `@<path>` tokens (regex `@([\w./\-]+\.\w+)`); for each, read `<repo>/<path>` (bounded: skip if missing or > `config.context_mention_max_chars` default 8000, truncate with marker); inject a `Message("user", f"<@{path}>\n{content}")` right after the user message in the assembled history. Cap total injected (e.g., first 3 mentions).

**Tests:** user msg `"look at @src/foo.py"` → assembled context contains `<@src/foo.py>` + file content; missing file → skipped (no crash); oversized → truncated marker.

- [ ] TDD → `feat(context): @mention file pull into chat context`.

---

## Task M4: `Retriever` (self-implemented symbol + grep)

**Files:** Create `src/harness/memory/retriever.py`. Test `tests/unit/test_retriever.py`.

**Interfaces (stdlib only):**
- `Retriever.symbols(root: str, max_files=200) -> dict[str, list[str]]`: walk `root` `.py` files (skip common ignore dirs `__pycache__`, `.git`, `.harness`), use `ast` to collect top-level + nested `FunctionDef`/`AsyncFunctionDef`/`ClassDef` names → `{name: ["file:line", ...]}`. Return dict.
- `Retriever.grep(pattern: str, root: str, max_hits=50) -> list[str]`: compile `pattern`, walk text files (`.py`/`.md`/`.toml`...), return `["file:line: snippet", ...]`.
- Both pure stdlib (§A.4-D self-implemented — no framework, no vector DB).

**Tests:** fixture repo with `src/foo.py` defining `add` → `symbols` has `add -> ["src/foo.py:<line>"]`; `grep("assert", root)` hits the test file lines; ignore dirs respected; `max_files`/`max_hits` caps.

- [ ] TDD → `feat(memory): self-implemented Retriever (ast symbols + grep)`.

---

## Self-Review
- §A.3 "记忆:按需提供给 LLM 而非全量载入": compaction (不全量载历史) + @mention (按需拉文件) + retriever (按需定位) — all three.
- §A.4-D: storage+retrieval self-implemented (stdlib ast/re), no framework memory.
- §A.4-C: all deterministic, mock-testable; build_chat integration via existing Message list.
- Compaction is structured (no LLM) → deterministic; an LLM-summarize option is future work.
