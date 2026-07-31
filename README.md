# harness — a self-coded Coding Agent Harness

A **conversational coding agent** (Claude/Codex-style CLI): you describe a task in natural language, the agent freely reads/edits files, runs shell commands and tests, self-corrects from test feedback, and asks before dangerous actions — all driven by a self-coded harness kernel around an LLM.

> **Agent = LLM + Harness.** The LLM only ever emits raw chat-completion text. Everything else — action parsing, governance (sandbox + diff preview), tool dispatch, deterministic feedback classification, context management (compaction + retrieval), task reporting — is **self-coded Python**. Swap in a `MockLLMClient` and the whole machine runs offline, deterministically, with zero network (§A.4-C).

**Three deep dimensions**: feedback loop (junit → taxonomy → strategy → stuck) + governance (sandbox + diff preview + task report) + memory/context (compaction + retrieval + @mention).

**Download**: [GitHub Release v1.0.0](https://github.com/MaxizYB/ai4se-coding-agent/releases/tag/v1.0.0)

---

## Install

Requires **Python ≥ 3.11** (uses stdlib `tomllib`).

```bash
# dev install (kernel + tests + lint; offline, no heavy deps)
pip install -e ".[dev]"

# full install (adds fastapi/uvicorn/httpx for the WebUI + real-LLM client)
pip install -e ".[full,dev]"
```

Core dependency is `cryptography` (for the credential store). FastAPI/uvicorn/httpx are only needed for the WebUI and the real GLM client.

---

## Configure credentials (§3.1 — required for real-LLM runs)

API keys are **never** hardcoded, committed, or logged. First run:

```bash
harness init
# choose a master password (hidden) → paste your ZHIPU API key (hidden)
# stores encrypted at ~/.harness/credentials.enc (Fernet + PBKDF2 ≥200k iters, mode 0o600)
```

Other commands:

```bash
harness key status     # shows "zhipu: set" — NEVER echoes the key
harness key set        # update the key (master password required)
harness key clear      # delete the store
```

Sources, in priority order: encrypted store (master password, or `HARNESS_MASTER_PASSWORD` env) → `ZHIPU_API_KEY` env var → `.env` file. **Plaintext risk:** env vars / `.env` are visible to the process environment and (for `.env`) on disk; prefer the encrypted store. The master password is unrecoverable (no backdoor).

---

## Run

### CLI — fix one failing test with the real LLM
```bash
harness fix --repo /path/to/project --test tests/test_foo.py::test_add
# prints "OUTCOME: SUCCESS|STUCK|BUDGET_EXHAUSTED|ERROR" + a unified diff of edits
# returns 0 on SUCCESS, 1 otherwise, 2 on missing credentials
```

### WebUI (§五.9) — demo mode (mock LLM, no key needed)
```bash
pip install -e ".[full,dev]"
HARNESS_DEMO_REPO=/path/to/demo/project uvicorn web.app:app --reload
# open http://localhost:8000 — submit a test selector, watch the loop stream turns
```

### Mechanism demo (§A.6) — fully offline, deterministic
```bash
make demo   # or: python scripts/mechanism_demo.py
# reproduces ① guardrail intercept ② feedback→action change ③ category-different hints
```

### Tests
```bash
make test     # pytest -m "not live"  (offline; the live GLM test is deselected)
make lint     # ruff check src tests scripts web
```

### Conversational REPL (Claude/Codex-style)
```bash
export ZHIPU_API_KEY="<your GLM key>"
harness chat --repo /path/to/project            # multi-turn; type tasks, /help for commands
harness chat --repo /path/to/project --accept tests/test_foo.py::test_add   # stop when green
harness task --repo /path/to/project --goal "add a login function"          # one-shot, non-interactive
```
The agent narrates each step, reads/edits files, runs tests to self-check (failure class + hint shown inline), and asks `y/N` before dangerous/network actions. Try it on the bundled sample:
```bash
harness chat --repo examples/demo --accept tests/test_foo.py::test_add
```

---

## Distribution

### Docker (primary)
```bash
docker build -t harness .
# fix a test (mount the target repo; key via env — note plaintext-in-env risk):
docker run --rm \
  -e ZHIPU_API_KEY=... \
  -v "$PWD":/work -w /work \
  harness fix --repo /work --test tests/test_foo.py::test_add
# smoke check (no key needed):
docker run --rm harness key status     # → (no keys stored)
```

### PyPI package (secondary)
The `harness` console script is declared in `pyproject.toml`. Build a wheel with `pip wheel .`; publishing to PyPI is the release step (CI `build-image` job builds the container).

---

## Configuration (`harness.toml`)

See `harness.toml.example`. All fields optional (safe defaults). Key knobs:

| Section | Field | Default | Meaning |
|---------|-------|---------|---------|
| `scope` | `allowed_write_dirs` | `["src"]` | Writes outside these are auto-denied (test dir read-only — the agent can't "cheat" by editing tests) |
| `guardrails` | `dangerous_shell_patterns` | … | Regex list → `AskHuman` (e.g. `rm -rf`, `git push --force`) |
| `guardrails` | `network_commands` | … | `pip install` / `curl` / … → `AskHuman` |
| `guardrails` | `fail_closed_when_noninteractive` | `true` | CI/batch: any `AskHuman` auto-denies (never hangs) |
| `budget` | `max_iterations` / `stuck_repeat_n` / `test_timeout_s` | 20 / 3 / 30 | Termination bounds |

---

## Directory structure

```
src/harness/
  agent.py              # AgentRunner main loop + termination (★ self-coded)
  cli.py                # harness init|key|fix
  config.py             # harness.toml loader
  credentials.py        # Fernet+PBKDF2 credential store (§3.1)
  types.py              # Message
  actions/{protocol,parser}.py     # typed Action union + text-protocol parser
  tools/{runner,dispatcher}.py     # pytest subprocess runner + tool executor
  guardrails/{guardrail,hitl}.py   # scope fence + dangerous/network gate + HITL
  feedback/{types,pytest_parser,classifier,strategy,stuck,engine}.py  # ★ deep dim
  context/manager.py    # engineered context-delivery layer
  memory/store.py       # notes + JSONL run-log
  llm/{base,mock,zhipu}.py   # LLM seam + offline mock + real GLM
web/{app.py,templates/}     # thin FastAPI WebUI (§五.9)
scripts/mechanism_demo.py   # §A.6 deterministic demo
tests/{unit,integration,fixtures}/   # 108 tests, offline
Dockerfile  .gitlab-ci.yml  Makefile  pyproject.toml  harness.toml.example
SPEC.md  PLAN.md  SPEC_PROCESS.md  AGENT_LOG.md  REFLECTION.md
```

---

## Security boundaries

- **Scope fence:** writes/edits must target `allowed_write_dirs` (default `src/`); path traversal (`../../`) and **symlinks pointing outside** the root are denied.
- **Dangerous/network commands:** matched against configurable patterns → `AskHuman` (HITL pause). In non-interactive mode (CI/batch) the approver is **fail-closed** → auto-deny.
- **Credentials:** encrypted at rest (Fernet + PBKDF2), file mode `0o600`, status never echoes plaintext, master password unrecoverable.
- **The harness only edits source under the configured scope and only runs the configured test command.** It does not exfiltrate (the LLM call is the only egress, to the configured provider).

## Known limitations

- Python ≥ 3.11; Linux is the primary target (symlink fence + `0o600` semantics tested on Linux).
- The WebUI ships in **demo mode** (mock LLM) so it runs without a key; driving a real run is via the CLI.
- The action protocol's `assert a == b` parser targets simple assertions (TDD red-green targets); composite/chained asserts fall back to `UNKNOWN`.
- Live GLM round-trip is covered by a gated `@pytest.mark.live` test (not run by default).

## License / third-party

Third-party deps: `cryptography`, `fastapi`, `uvicorn`, `httpx`, `pytest`, `ruff` (see `pyproject.toml`). Built with the [Superpowers](https://github.com/obra/superpowers) methodology (brainstorming → writing-plans → cold-start validation → subagent-driven-development → TDD → code review → finishing-a-development-branch).
