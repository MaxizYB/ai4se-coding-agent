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
    from harness.guardrails.sandbox import Sandbox
    from harness.guardrails.sandbox_docker import SandboxDockerExecutor
    from harness.memory.store import MemoryStore
    from harness.tools.dispatcher import ToolDispatcher
    cfg = load_config(args.config); cfg.project_root = args.repo
    mem = MemoryStore(os.path.join(args.repo, "HARNESS.md"), os.path.join(args.repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    # I2: credential resolution is shared with the chat/task subcommands via
    # _resolve_llm() (store-first, then ZHIPU_API_KEY env). No duplicated logic.
    llm = _resolve_llm()
    if llm is None:
        print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
    # G5: build the hard-isolation executor only when containerize is opted in;
    # otherwise pass None and the loop falls back to host dispatch.
    sde = SandboxDockerExecutor(cfg) if cfg.sandbox_containerize else None
    runner = AgentRunner(llm, cfg, ToolDispatcher(cfg), Guardrail(cfg), HITL(FailClosedApprover()),
                         FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m,
                                        cfg.hint_history_lines), cm, sandbox=Sandbox(cfg), sandbox_docker=sde)
    result = runner.run(Task(args.repo, args.test))
    print(f"OUTCOME: {result.outcome}")
    print(result.edits_diff)
    return 0 if result.outcome == "SUCCESS" else 1

def _resolve_llm():
    """Return (llm_client_or_None). Encrypted store first (master pw), then ZHIPU_API_KEY env.

    The getpass prompt is gated on the store file existing so a no-creds / no-tty
    environment (CI, tests) resolves to None instead of hanging on input.
    """
    import getpass as gp

    from harness.llm.zhipu import ZhipuLLMClient
    st = CredentialStore(os.path.expanduser("~/.harness/credentials.enc"))
    if os.path.exists(st.path):
        try:
            master = os.environ.get("HARNESS_MASTER_PASSWORD") or gp.getpass("Master password: ")
            return ZhipuLLMClient("glm-4.6", st.get("zhipu", master))
        except (CredentialError, EOFError, OSError):
            # CredentialError: wrong master / corrupt store → env fallback.
            # EOFError/OSError: no TTY / piped stdin (CI, containers) → the
            # getpass prompt cannot be satisfied; fall through to the env
            # branch instead of crashing. (I3)
            pass
    env_key = os.environ.get("ZHIPU_API_KEY")
    if env_key:
        return ZhipuLLMClient("glm-4.6", env_key)
    return None


def _build_chat_components(args):
    from harness.context.manager import ContextManager
    from harness.feedback.engine import FeedbackEngine
    from harness.guardrails.guardrail import Guardrail
    from harness.guardrails.sandbox import Sandbox
    from harness.guardrails.sandbox_docker import SandboxDockerExecutor
    from harness.memory.store import MemoryStore
    from harness.tools.dispatcher import ToolDispatcher
    cfg = load_config(getattr(args, "config", None)); cfg.project_root = args.repo
    mem = MemoryStore(os.path.join(args.repo, "HARNESS.md"), os.path.join(args.repo, ".harness", "run.jsonl"))
    cm = ContextManager(cfg, mem)
    fe = FeedbackEngine(cfg.test_timeout_s, cfg.stuck_repeat_n, cfg.stuck_no_progress_m, cfg.hint_history_lines)
    # G5: hard-isolation executor only when opted in; None otherwise.
    sde = SandboxDockerExecutor(cfg) if cfg.sandbox_containerize else None
    return cfg, ToolDispatcher(cfg), Guardrail(cfg), fe, cm, Sandbox(cfg), sde


def _cmd_chat(args):
    from harness.guardrails.hitl import HITL, ConsoleApprover
    from harness.interactive.chat import ChatRunner
    llm = _resolve_llm()
    if llm is None:
        print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
    cfg, disp, gr, fe, cm, sb, sde = _build_chat_components(args)
    ChatRunner(llm, cfg, disp, gr, HITL(ConsoleApprover()), fe, cm, sandbox=sb, sandbox_docker=sde).run(args.repo, accept=args.accept)
    return 0


def _cmd_task(args):
    from harness.guardrails.hitl import HITL, FailClosedApprover
    from harness.interactive.chat import ChatRunner
    llm = _resolve_llm()
    if llm is None:
        print("no credentials (run `harness init` or set ZHIPU_API_KEY)", file=sys.stderr); return 2
    cfg, disp, gr, fe, cm, sb, sde = _build_chat_components(args)
    runner = ChatRunner(llm, cfg, disp, gr, HITL(FailClosedApprover()), fe, cm, sandbox=sb, sandbox_docker=sde)
    return runner.run_task(args.repo, args.goal, accept=args.accept)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="harness")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=_cmd_init)
    pk = sub.add_parser("key"); pk.add_argument("sub", choices=["status", "set", "clear"]); pk.set_defaults(func=_cmd_key)
    pf = sub.add_parser("fix"); pf.add_argument("--repo", required=True); pf.add_argument("--test", required=True)
    pf.add_argument("--config", default=None); pf.set_defaults(func=_cmd_fix)
    pc = sub.add_parser("chat"); pc.add_argument("--repo", required=True)
    pc.add_argument("--accept", default=None); pc.add_argument("--config", default=None)
    pc.set_defaults(func=_cmd_chat)
    pt = sub.add_parser("task"); pt.add_argument("--repo", required=True)
    pt.add_argument("--goal", required=True); pt.add_argument("--accept", default=None)
    pt.add_argument("--config", default=None); pt.set_defaults(func=_cmd_task)
    args = p.parse_args(argv)
    return args.func(args)
