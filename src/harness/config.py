import tomllib
from dataclasses import dataclass, field


@dataclass
class Config:
    project_root: str = "."
    allowed_write_dirs: list[str] = field(default_factory=lambda: ["src"])
    dangerous_shell_patterns: list[str] = field(default_factory=list)
    network_commands: list[str] = field(default_factory=lambda: ["pip install"])
    fail_closed_when_noninteractive: bool = True
    max_iterations: int = 20
    max_parse_failures: int = 5
    stuck_repeat_n: int = 3
    stuck_no_progress_m: int = 4
    test_timeout_s: int = 30
    hint_history_lines: int = 8
    max_history: int = 8
    # Sandbox: HARD execution-boundary gate (Guardrail asks a human; Sandbox
    # says no regardless). Deterministic, mock-testable. See sandbox.py.
    sandbox_network: str = "allowlist"
    sandbox_network_allow: list[str] = field(default_factory=list)
    sandbox_denied_commands: list[str] = field(
        default_factory=lambda: [
            r"rm\s+-rf\s+/",
            r"mkfs",
            r"dd\s+.*\bof=",
            r":\(\)\s*\{",
            r">\s*/dev/sd",
            r"sudo",
        ]
    )
    sandbox_write_roots: list[str] = field(default_factory=lambda: ["src"])
    sandbox_containerize: bool = False
    sandbox_container_image: str = "python:3.11-slim"

    @classmethod
    def default(cls) -> "Config":
        return cls()


def load_config(path: str | None) -> Config:
    cfg = Config.default()
    if path is None:
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)
    scope = data.get("scope", {})
    gr = data.get("guardrails", {})
    bud = data.get("budget", {})
    fb = data.get("feedback", {})
    ctx = data.get("context", {})
    sb = data.get("sandbox", {})
    cfg.project_root = scope.get("project_root", cfg.project_root)
    cfg.allowed_write_dirs = scope.get("allowed_write_dirs", cfg.allowed_write_dirs)
    cfg.dangerous_shell_patterns = gr.get("dangerous_shell_patterns", cfg.dangerous_shell_patterns)
    cfg.network_commands = gr.get("network_commands", cfg.network_commands)
    cfg.fail_closed_when_noninteractive = gr.get("fail_closed_when_noninteractive", cfg.fail_closed_when_noninteractive)
    cfg.max_iterations = bud.get("max_iterations", cfg.max_iterations)
    cfg.max_parse_failures = bud.get("max_parse_failures", cfg.max_parse_failures)
    cfg.stuck_repeat_n = bud.get("stuck_repeat_n", cfg.stuck_repeat_n)
    cfg.stuck_no_progress_m = bud.get("stuck_no_progress_m", cfg.stuck_no_progress_m)
    cfg.test_timeout_s = bud.get("test_timeout_s", cfg.test_timeout_s)
    cfg.hint_history_lines = fb.get("hint_history_lines", cfg.hint_history_lines)
    cfg.max_history = ctx.get("max_history", cfg.max_history)
    cfg.sandbox_network = sb.get("network", cfg.sandbox_network)
    cfg.sandbox_network_allow = sb.get("network_allow", cfg.sandbox_network_allow)
    cfg.sandbox_denied_commands = sb.get("denied_commands", cfg.sandbox_denied_commands)
    cfg.sandbox_write_roots = sb.get("write_roots", cfg.sandbox_write_roots)
    cfg.sandbox_containerize = sb.get("containerize", cfg.sandbox_containerize)
    cfg.sandbox_container_image = sb.get("container_image", cfg.sandbox_container_image)
    return cfg
