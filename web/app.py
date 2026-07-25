import json
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from harness.agent import AgentRunner, Task
from harness.config import Config
from harness.context.manager import ContextManager
from harness.feedback.engine import FeedbackEngine
from harness.guardrails.guardrail import Guardrail
from harness.guardrails.hitl import HITL, FailClosedApprover
from harness.llm.mock import MockLLMClient
from harness.memory.store import MemoryStore
from harness.tools.dispatcher import ToolDispatcher

app = FastAPI()

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")


class RunReq(BaseModel):
    test: str


@app.get("/", response_class=HTMLResponse)
def index():
    with open(_TEMPLATE_PATH) as f:
        return f.read()


def _runner(repo: str):
    cfg = Config.default()
    cfg.project_root = repo
    mem = MemoryStore(
        os.path.join(repo, "HARNESS.md"),
        os.path.join(repo, ".harness", "run.jsonl"),
    )
    cm = ContextManager(cfg, mem)
    t = "tests/test_foo.py::test_add"
    script = [
        "ACTION: run_tests\nARGS: {t}\n",
        "ACTION: edit_file\nPATH: src/foo.py\n<<<OLD\n    return a - b\n>>>OLD\n<<<NEW\n    return a + b\n>>>NEW\n",
        "ACTION: run_tests\nARGS: {t}\n",
        "ACTION: finish\nREASON: green\n",
    ]
    return AgentRunner(
        MockLLMClient([s.format(t=t) for s in script]),
        cfg,
        ToolDispatcher(cfg),
        Guardrail(cfg),
        HITL(FailClosedApprover()),
        FeedbackEngine(
            cfg.test_timeout_s,
            cfg.stuck_repeat_n,
            cfg.stuck_no_progress_m,
            cfg.hint_history_lines,
        ),
        cm,
    )


@app.post("/run")
def run(req: RunReq):
    repo = os.environ.get("HARNESS_DEMO_REPO", ".")
    runner = _runner(repo)

    def stream():
        result = runner.run(Task(repo, req.test))
        for t in result.turns:
            yield (
                json.dumps(
                    {"turn": t.action, "decision": t.decision, "summary": t.summary}
                )
                + "\n"
            )
        yield json.dumps({"outcome": result.outcome, "diff": result.edits_diff}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
