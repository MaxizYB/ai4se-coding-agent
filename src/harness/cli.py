import argparse
import getpass
import os
import sys

from harness.config import load_config
from harness.credentials import CredentialError, CredentialStore


def _store():
    path = os.path.expanduser("~/.harness/credentials.enc")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return CredentialStore(path)

def _cmd_init(args):
    master = getpass.getpass("Choose master password: ")
    key = getpass.getpass("ZHIPU API key: ").strip()
    _store().set("zhipu", key, master)
    print("credentials stored (encrypted).")
    return 0

def _cmd_key(args):
    st = _store()
    if args.sub == "status":
        for provider, set_ in st.status().items():
            print(f"{provider}: {'set' if set_ else 'unset'}")
        if not st.status():
            print("(no keys stored)")
        return 0
    if args.sub == "set":
        master = getpass.getpass("Master password: ")
        key = getpass.getpass("New ZHIPU API key: ").strip()
        st.set("zhipu", key, master); print("updated."); return 0
    if args.sub == "clear":
        st.clear(); print("cleared."); return 0
    return 1  # unreachable: argparse `choices` rejects unknown subcommands

def _cmd_fix(args):
    from harness.agent import AgentRunner, Task
    from harness.context.manager import ContextManager
    from harness.feedback.engine import FeedbackEngine
    from harness.guardrails.guardrail import Guardrail
    from harness.guardrails.hitl import HITL, FailClosedApprover
    from harness.memory.store import MemoryStore
    from harness.tools.dispatcher import ToolDispatcher
    cfg = load_config(args.config); cfg.project_root = args.repo
    mem = MemoryStore(os.path.join(args.repo, "HARNESS.md"), os.path.join(args.repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    runner = AgentRunner(None, cfg, ToolDispatcher(cfg), Guardrail(cfg), HITL(FailClosedApprover()),
                         FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m,
                                        cfg.hint_history_lines), cm)
    # wire real LLM only when key available
    try:
        master = os.environ.get("HARNESS_MASTER_PASSWORD") or getpass.getpass("Master password: ")
        key = _store().get("zhipu", master)
        from harness.llm.zhipu import ZhipuLLMClient
        runner.llm = ZhipuLLMClient("glm-4.6", key)
    except CredentialError:
        env_key = os.environ.get("ZHIPU_API_KEY")
        if not env_key:
            print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
        from harness.llm.zhipu import ZhipuLLMClient
        runner.llm = ZhipuLLMClient("glm-4.6", env_key)
    result = runner.run(Task(args.repo, args.test))
    print(f"OUTCOME: {result.outcome}")
    print(result.edits_diff)
    return 0 if result.outcome == "SUCCESS" else 1

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="harness")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=_cmd_init)
    pk = sub.add_parser("key"); pk.add_argument("sub", choices=["status", "set", "clear"]); pk.set_defaults(func=_cmd_key)
    pf = sub.add_parser("fix"); pf.add_argument("--repo", required=True); pf.add_argument("--test", required=True)
    pf.add_argument("--config", default=None); pf.set_defaults(func=_cmd_fix)
    args = p.parse_args(argv)
    return args.func(args)
