"""FastAPI presentation layer for the harness coding agent.

The web process owns no agent logic. It creates a runner, translates presenter
callbacks to newline-delimited JSON, and keeps the public demo inside a
throwaway copy of ``examples/demo`` when isolation is enabled.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from harness.agent import AgentRunner, Task
from harness.config import Config
from harness.context.manager import ContextManager
from harness.feedback.engine import FeedbackEngine
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.guardrails.sandbox import Sandbox
from harness.interactive.chat import ChatRunner
from harness.llm.mock import MockLLMClient
from harness.memory.store import MemoryStore
from harness.tools.dispatcher import ToolDispatcher
from harness.types import Message
from web.presenter import WebPresenter

_TEMPLATE_PATH = Path(__file__).with_name("templates") / "index.html"
_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
_MAX_MESSAGE_CHARS = 8_000
_MAX_HISTORY = 16
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
_RUN_SLOTS = threading.BoundedSemaphore(2)

app = FastAPI(title="harness - Coding Agent", version="1.0.0")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=_MAX_MESSAGE_CHARS)
    mode: str = Field(default="demo", pattern="^(demo|real)$")
    key: str = Field(default="", max_length=512)
    base_url: str = Field(default=_DEFAULT_BASE_URL, max_length=300)
    model: str = Field(default="glm-4.6", max_length=80)
    repo: str = Field(default="", max_length=500)
    accept: str = Field(default="tests/test_foo.py::test_add", max_length=300)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=_MAX_HISTORY)

    @field_validator("message", "key", "base_url", "model", "repo", "accept", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("model")
    @classmethod
    def valid_model(cls, value: str) -> str:
        if not _MODEL_RE.fullmatch(value):
            raise ValueError("model contains unsupported characters")
        return value

    @field_validator("history")
    @classmethod
    def valid_history(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        clean = []
        for item in value[-_MAX_HISTORY:]:
            if item.get("role") not in {"user", "assistant"}:
                continue
            content = item.get("content", "")
            if isinstance(content, str) and content.strip():
                clean.append({"role": item["role"], "content": content[:_MAX_MESSAGE_CHARS]})
        return clean


class RunReq(BaseModel):
    """Compatibility payload for the original ``POST /run`` demo endpoint."""

    test: str = Field(min_length=1, max_length=300)
    key: str = Field(default="", max_length=512)
    goal: str = Field(default="", max_length=_MAX_MESSAGE_CHARS)


def _demo_root() -> Path:
    configured = os.environ.get("HARNESS_DEMO_REPO")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / "examples" / "demo").resolve()


def _resolve_repo(requested: str) -> tuple[str, Callable[[], None]]:
    """Resolve a repository and return ``(path, cleanup)``.

    Deployed instances accept only the bundled demo repository. Local users can
    opt into a custom path with ``HARNESS_ALLOW_CUSTOM_REPO=1``. Isolation is
    useful for a public demo because every request starts from a clean fixture.
    """

    demo = _demo_root()
    allow_custom = os.environ.get("HARNESS_ALLOW_CUSTOM_REPO") == "1"
    candidate = Path(requested).expanduser().resolve() if requested else demo
    if not allow_custom and candidate != demo:
        raise HTTPException(status_code=403, detail="custom repositories are disabled on this deployment")
    if not candidate.is_dir():
        raise HTTPException(status_code=400, detail=f"repository does not exist: {candidate}")

    # Isolation is the secure default. Set HARNESS_ISOLATE_DEMO=0 only for a
    # local debugging session where preserving edits in the fixture is useful.
    isolate = os.environ.get("HARNESS_ISOLATE_DEMO", "1") != "0" and candidate == demo
    if not isolate:
        return str(candidate), lambda: None
    temp = Path(tempfile.mkdtemp(prefix="harness-demo-")) / "repo"
    shutil.copytree(candidate, temp)
    return str(temp), lambda: shutil.rmtree(temp.parent, ignore_errors=True)


def _validate_base_url(value: str) -> str:
    parsed = urlparse(value)
    custom = os.environ.get("HARNESS_ALLOW_CUSTOM_BASE_URL") == "1"
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=400, detail="base_url must be an HTTPS URL")
    if not custom and parsed.netloc.lower() != "open.bigmodel.cn":
        raise HTTPException(status_code=403, detail="custom model endpoints are disabled on this deployment")
    return value.rstrip("/")


def _demo_script(selector: str) -> list[str]:
    return [
        "I will reproduce the failing test first.\nACTION: run_tests\nARGS: {t}\n",
        (
            "The failure points at the implementation. I will make the smallest source edit.\n"
            "ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n"
            "<<<NEW\n    return a + b\n>>>NEW\n"
        ),
        "The implementation is updated; I will verify the acceptance test.\nACTION: run_tests\nARGS: {t}\n",
        "The acceptance test is green.\nACTION: finish\nREASON: verified\n",
    ]


def _build_runner(req: ChatRequest, presenter: WebPresenter, repo: str):
    cfg = Config.default()
    cfg.project_root = repo
    # ``always`` exposes the exact unified diff in the stream while remaining
    # non-interactive: it previews, then applies without waiting for stdin.
    cfg.diff_preview = "always"
    mem = MemoryStore(os.path.join(repo, "HARNESS.md"), os.path.join(repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    if req.mode == "real":
        if not req.key:
            raise HTTPException(status_code=400, detail="an API key is required in real mode")
        from harness.llm.zhipu import ZhipuLLMClient

        llm = ZhipuLLMClient(req.model, req.key, base_url=_validate_base_url(req.base_url))
    else:
        llm = MockLLMClient([item.format(t=req.accept) for item in _demo_script(req.accept)])
    runner = ChatRunner(
        llm,
        cfg,
        ToolDispatcher(cfg),
        Guardrail(cfg),
        HITL(FailClosedApprover()),
        FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines),
        cm,
        presenter=presenter,
        sandbox=Sandbox(cfg),
    )
    return runner


def _stream_queue(q: queue.Queue, cleanup=lambda: None) -> Iterator[str]:
    try:
        while True:
            try:
                item = q.get(timeout=180)
            except queue.Empty:
                yield json.dumps({"type": "error", "message": "agent timed out"}, ensure_ascii=False) + "\n"
                break
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"
    finally:
        cleanup()
        _RUN_SLOTS.release()


@app.get("/", response_class=HTMLResponse)
def index():
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


@app.get("/api/info")
def info():
    return {
        "name": "harness",
        "version": app.version,
        "description": "A deterministic coding-agent harness around an LLM",
        "features": ["feedback loop", "sandbox and diff governance", "memory and retrieval", "streaming chat"],
        "default_model": "glm-4.6",
        "demo_isolated": os.environ.get("HARNESS_ISOLATE_DEMO", "1") != "0",
        "custom_repo": os.environ.get("HARNESS_ALLOW_CUSTOM_REPO") == "1",
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not _RUN_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="two agent runs are already in progress")
    try:
        repo, cleanup = _resolve_repo(req.repo)
        try:
            q: queue.Queue = queue.Queue()
            presenter = WebPresenter(q)
            runner = _build_runner(req, presenter, repo)
        except Exception:
            cleanup()
            raise
        history = [Message(item["role"], item["content"]) for item in req.history]
        history.append(Message("user", req.message))

        def run_agent():
            try:
                outcome = runner._agent_loop(repo, req.accept or None, history)
                presenter.show_turn_end(outcome)
            except Exception as exc:  # noqa: BLE001  # never leak a traceback or key
                q.put({"type": "error", "message": str(exc)[:500]})
            finally:
                q.put(None)

        threading.Thread(target=run_agent, daemon=True).start()
        return StreamingResponse(_stream_queue(q, cleanup), media_type="application/x-ndjson")
    except Exception:
        _RUN_SLOTS.release()
        raise


@app.post("/run")
def run_legacy(req: RunReq):
    """Keep the original deterministic red-green endpoint for existing links."""

    if not _RUN_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="two agent runs are already in progress")
    try:
        repo, cleanup = _resolve_repo("")
        cfg = Config.default()
        cfg.project_root = repo
        cfg.diff_preview = "never"
        mem = MemoryStore(os.path.join(repo, "HARNESS.md"), os.path.join(repo, ".harness", "run.jsonl"))
        cm = ContextManager(cfg, mem)
        q: queue.Queue = queue.Queue()

        if req.key:
            from harness.llm.zhipu import ZhipuLLMClient

            runner = ChatRunner(
                ZhipuLLMClient("glm-4.6", req.key), cfg, ToolDispatcher(cfg), Guardrail(cfg),
                HITL(FailClosedApprover()),
                FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines),
                cm, presenter=WebPresenter(q), sandbox=Sandbox(cfg),
            )

            def run_agent():
                try:
                    outcome = runner._agent_loop(repo, req.test, [Message("user", req.goal or f"make {req.test} pass")])
                    runner.presenter.show_turn_end(outcome)
                except Exception as exc:  # noqa: BLE001
                    q.put({"type": "error", "message": str(exc)[:500]})
                finally:
                    q.put(None)
        else:
            script = [item.format(t=req.test) for item in _demo_script(req.test)]
            runner = AgentRunner(
                MockLLMClient(script), cfg, ToolDispatcher(cfg), Guardrail(cfg), HITL(FailClosedApprover()),
                FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines),
                cm, sandbox=Sandbox(cfg),
            )

            def run_agent():
                try:
                    result = runner.run(Task(repo, req.test))
                    for turn in result.turns:
                        q.put({"turn": turn.action, "decision": turn.decision, "summary": turn.summary})
                    q.put({"outcome": result.outcome, "diff": result.edits_diff})
                except Exception as exc:  # noqa: BLE001
                    q.put({"type": "error", "message": str(exc)[:500]})
                finally:
                    q.put(None)

        threading.Thread(target=run_agent, daemon=True).start()
        return StreamingResponse(_stream_queue(q, cleanup), media_type="application/x-ndjson")
    except Exception:
        _RUN_SLOTS.release()
        raise
