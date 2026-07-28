# ARCHITECTURE.md — harness 编码 agent 内核架构文档

> 本文档供理解与上手:从"一台什么机器"到"每个文件干什么"到"怎么扩展"。
> 源码 2420 行 / 30 模块 / 33 测试文件 / 234 测试。所有机制都是确定性代码(§A.4-B/C:换 mock LLM 仍可单测)。

---

## 1. 它是什么

**harness = 把"只会说下一句话的 LLM"封装成"能稳定干活的编码 agent"的那层工程。**

核心等式:**Agent = LLM + Harness**。LLM(GLM-4.6)只出原始文本——决定"下一步做什么"。其余全是 `src/harness/` 里自编写的 Python:
- 读/写/编辑文件、执行 shell、跑测试(**工具**)
- 在危险动作前拦截、限制写入范围、可选容器隔离(**治理**)
- 把测试输出解析成失败分类、策略 hint、卡住检测(**反馈闭环**)
- 长对话压缩、项目记忆、按需拉文件、符号检索(**记忆/上下文**)
- 结构化任务总结(**报告**)

换掉 `ZhipuLLMClient` 为 `MockLLMClient`,整台机器离线、确定性跑(234 个测试不用网)。

**两种入口**:`harness chat`(交互 REPL,类 Claude Code)、`harness task`(一次性,管道/脚本用)。

---

## 2. 架构总览

```
用户消息
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│  ChatRunner / AgentRunner  (主循环)                       │
│                                                          │
│  1. ContextManager.build_chat                            │
│     ├─ 系统提示 (ACT/REPLY 协议 + 范例)                    │
│     ├─ AGENTS.md / HARNESS.md (项目记忆)                   │
│     ├─ Compactor.maybe_compact (超阈值→压缩旧轮)            │
│     ├─ @mention 解析 (用户消息 @path → 文件内容注入)         │
│     └─ 历史 (bounded, 保留最近 K 轮)                       │
│                                                          │
│  2. LLMClient.complete(ctx) → 原始文本                    │
│     ├─ MockLLMClient (离线测试)                           │
│     └─ ZhipuLLMClient (真实 GLM-4.6)                      │
│                                                          │
│  3. split_prose_and_action(raw) → (prose, Action|None)   │
│     ├─ 无 ACTION → REPLIED (结束轮次,回用户)                │
│     └─ ParseError → 回灌错误,重试 (≤ max_parse_failures)   │
│                                                          │
│  4. Guardrail.check(action) → Allow/Deny/AskHuman         │
│     ├─ 文件 scope fence (越界写→Deny)                      │
│     └─ 危险/网络命令→AskHuman                              │
│                                                          │
│  5. HITL.request (若 AskHuman)                            │
│     ├─ ConsoleApprover: 交互 y/N                         │
│     └─ FailClosedApprover: 非交互自动拒                   │
│                                                          │
│  6. Sandbox.check(action) → Allow/Deny/AskHuman/Container │
│     ├─ 命令 denylist (硬拒 rm -rf/mkfs/sudo)              │
│     ├─ 网络 egress (allowlist/offline/open)               │
│     ├─ FS write_roots (realpath, 防 symlink)              │
│     └─ Containerize → SandboxDockerExecutor (可选 Docker) │
│                                                          │
│  7. DiffGate (若 write/edit + ask 模式)                   │
│     ├─ DiffPreviewer.preview → unified diff              │
│     └─ HITL 审批 → 放行/跳过                               │
│                                                          │
│  8. ToolDispatcher.execute(action) → ToolResult          │
│     ├─ read_file / list_dir / write_file / edit_file     │
│     ├─ run_shell (可选 STDIN 管道)                        │
│     └─ run_tests (pytest --junitxml, 绝对路径)            │
│                                                          │
│  9. 若 RunTests → FeedbackEngine.classify                 │
│     ├─ pytest_parser: junit XML → TestRunResult          │
│     ├─ classifier: ENV/LOGIC/TIMEOUT/UNKNOWN             │
│     ├─ strategy: 分类→确定性 hint                          │
│     ├─ stuck: 签名重复/无进展→STUCK                        │
│     └─ → FailureReport 回灌下一轮                          │
│                                                          │
│ 10. task_events 追加 (file_changed/shell/test)             │
│                                                          │
│ 11. 终止: Finish/SUCCESS/REPLIED/BUDGET/ERROR             │
│     └─ TaskReport.build → presenter.show_report           │
└──────────────────────────────────────────────────────────┘
    │
    ▼
用户看到: prose + 动作 + 结果 + 反馈 + 报告
```

---

## 3. 主循环详解(一个 turn 的完整生命周期)

**最该读懂的一段代码**: `src/harness/interactive/chat.py::_agent_loop` (~70 行)。以下按顺序拆解:

### 3.1 组装上下文
```
ContextManager.build_chat(repo, accept, history)
```
- 系统提示(`_CHAT_SYSTEM`):角色 + ACT/REPLY 两模式 + 协议格式 + 精确范例。
- AGENTS.md(若 `<repo>/AGENTS.md` 存在)→ 项目记忆 system 消息。
- HARNESS.md notes(若 MemoryStore 有)→ 项目约定。
- **Compactor.maybe_compact(history)**:若 `sum(len) > compact_threshold(6000)`,把旧轮压成 1 条 `[compacted history]` 事实 system 消息(结构化、无 LLM),保留最近 `keep_recent(6)` 轮。
- **@mention 解析**:最后一条 user 消息里的 `@<path>` → 读文件内容注入(realpath 防遍历)。
- 历史裁剪到 `max_history(8)` 轮(保证 summary 不被切掉)。

### 3.2 调 LLM
```
raw = self.llm.complete(ctx)   # 唯一碰 LLM 的地方
```
- `MockLLMClient`:按脚本返回写死的动作序列(测试用)。
- `ZhipuLLMClient`:httpx POST 智谱 chat-completions,lazy-import httpx(保默认套件离线)。

### 3.3 解析
```
prose, action = split_prose_and_action(raw)
```
- prose = ACTION 之前的文本(agent 的"述词")。
- action = `parse_action(raw)` 提取的 typed Action。
- 无 ACTION → `(raw, None)` → **REPLIED**(结束轮次,回用户提示符)。Claude/Codex 语义:纯文本 = 对话回复,不是干活。

### 3.4 治理链(三道门)
```
guardrail.check(action)  →  Allow/Deny/AskHuman
   ↓ (AskHuman → hitl.request)
sandbox.check(action)    →  Allow/Deny/AskHuman/Containerize
   ↓ (AskHuman → hitl.request; Containerize → docker executor)
diff_gate(action)        →  approve/skip (仅 write/edit)
   ↓
dispatcher.execute(action)
```
- **Guardrail**(`guardrails/guardrail.py`):scope fence + AskHuman(问人)。
- **Sandbox**(`guardrails/sandbox.py`):硬边界(denylist 硬拒 / 网络 egress / FS write_roots)。Sandbox 是"无论如何不许"的层,在 Guardrail(问人)之上。
- **DiffGate**(`governance/diff_preview.py`):write/edit 前展示 unified diff + 审批。
- **HITL**(`guardrails/hitl.py`):`Approver` Protocol 注入——`ConsoleApprover`(交互 y/N)/ `FailClosedApprover`(CI 自动拒)/ `StubApprover`(测试)。

### 3.5 执行
```
result = self.dispatcher.execute(action)
```
- `read_file`/`list_dir`/`write_file`/`edit_file`/`run_shell`/`run_tests`。
- `run_shell` 支持可选 `STDIN`(多行)管道→驱动交互程序。
- `run_tests` 用绝对路径 junit(`--junitxml=<abs>`)确保 FeedbackEngine 能读到。

### 3.6 反馈(若 RunTests)
```
fb = self.feedback_engine.classify(result)
```
- **FeedbackEngine** 是项目的**主要深做贡献**:
  - `pytest_parser`:junit XML → `TestRunResult`(含 `exit_code`,真实 pytest 无 `type=` 时从 message 推断 exc_type)。
  - `classifier`:`ENV`(import/collection/syntax) / `LOGIC`(assert/attr/name/type/value) / `TIMEOUT` / `UNKNOWN`。
  - `strategy`:每类 → 确定性 hint("修实现逻辑" vs "查依赖/导入" vs "重审算法")。
  - `stuck`:失败签名(忽略顺序/行号)重复 N 轮 / 无进展 M 轮 → STUCK。
  - → `FailureReport` 回灌下一轮(经 `presenter.show_feedback` 显示 + 经 context_manager 注入)。
- 若 `accept` 测试绿 → `SUCCESS`(客观停机信号)。

### 3.7 终止 + 报告
```
TaskReport.build(task_events, outcome, summary)
presenter.show_report(report)
```
- `task_events`:本轮的结构化事件列表(file_changed / shell / test)。
- `TaskReport`:`{outcome, files_changed[], commands_run[], tests[], summary}`。
- `presenter.show_report`:渲染为用户可读的报告块。

---

## 4. 三大深做维度

作业 §A.4-D 要求"选一个维度深做"。本项目有**三个深做维度**(反馈为主,治理+记忆为提升):

### 4.1 反馈闭环(主要贡献,§A.4-D 反馈)

| 子件 | 文件 | 职责 |
|------|------|------|
| 类型 | `feedback/types.py` | `FailureCategory`/`TestFailure`/`TestRunResult`/`FailureReport` |
| 解析器 | `feedback/pytest_parser.py` | junit XML → 结构化(含无 `type=` 推断) |
| 分类器 | `feedback/classifier.py` | exc_type → ENV/LOGIC/TIMEOUT/UNKNOWN(裸名匹配) |
| 策略 | `feedback/strategy.py` | 分类 → 确定性 hint |
| 卡住 | `feedback/stuck.py` | 签名重复/无进展 → STUCK |
| 引擎 | `feedback/engine.py` | 串联以上 → `FailureReport` |

**为什么深做**:反馈信号是 coding agent 最客观的"行为是否正确"信号(红→绿)。确定性 + 可 mock 单测(§A.4-C 硬判据)。是 §A.6 机制演示②的中心展品。

### 4.2 治理(§A.4-D 治理/沙箱)

| 子件 | 文件 | 职责 |
|------|------|------|
| Guardrail | `guardrails/guardrail.py` | scope fence(文件越界)+ AskHuman(危险/网络) |
| Sandbox | `guardrails/sandbox.py` | 硬边界:denylist + 网络 egress + write_roots(realpath) |
| HITL | `guardrails/hitl.py` | Approver Protocol:Console/FailClosed/Stub |
| Docker | `guardrails/sandbox_docker.py` | 可选容器隔离(--network=none --read-only) |
| DiffGate | `governance/diff_preview.py` | write 前 unified diff + 审批 |
| TaskReport | `governance/task_report.py` | 结构化任务总结 |

**三层防御**:Guardrail(问人)→ Sandbox(硬拒)→ DiffGate(审查变更)。每层都是独立确定性代码机制。

### 4.3 记忆/上下文(§A.4-D 记忆/上下文)

| 子件 | 文件 | 职责 |
|------|------|------|
| Compactor | `memory/compactor.py` | 超阈值→旧轮压成事实摘要(无 LLM,确定性) |
| AGENTS.md | `context/manager.py` | 项目记忆自动载入 |
| @mention | `context/manager.py` | `@path` → 文件内容注入(realpath 防遍历) |
| Retriever | `memory/retriever.py` | 自实现:ast 符号索引 + regex grep |
| MemoryStore | `memory/store.py` | 跨会话:HARNESS.md notes + JSONL run-log |

**§A.4-D 要求自实现**:Compactor 用 stdlib 结构化摘要(不调 LLM);Retriever 用 ast+re(不接向量库)。

---

## 5. 模块参考(按职责分组)

### 5.1 决策层(主循环)
| 文件 | 职责 | 关键类型 |
|------|------|---------|
| `interactive/chat.py` | 交互 REPL + agent loop + 斜杠命令 | `ChatRunner.run()` `_agent_loop()` |
| `agent.py` | 批处理主循环(fix 模式) | `AgentRunner.run(task)` |
| `cli.py` | argparse: init/key/fix/chat/task | `main(argv)` |

### 5.2 工具层(动作 + 执行)
| 文件 | 职责 | 关键类型 |
|------|------|---------|
| `actions/protocol.py` | 7 个 typed Action | `ReadFile` `WriteFile` `EditFile` `RunShell` `RunTests` `Finish` `ListDir` |
| `actions/parser.py` | 文本协议→Action;`split_prose_and_action` | `parse_action(text)` `ParseError` |
| `tools/dispatcher.py` | 执行 Action→ToolResult | `ToolDispatcher.execute(action)` |
| `tools/runner.py` | pytest 子进程 + junit + 超时 | `run_tests(cmd, cwd, timeout, junit_path)` |

### 5.3 治理层
| 文件 | 职责 | 关键类型 |
|------|------|---------|
| `guardrails/guardrail.py` | scope fence + AskHuman | `Guardrail.check()` `Allow/Deny/AskHuman` |
| `guardrails/sandbox.py` | 硬边界:denylist/egress/write_roots | `Sandbox.check()` `Containerize` |
| `guardrails/hitl.py` | 审批状态机 | `HITL.request()` `Console/FailClosed/StubApprover` |
| `guardrails/sandbox_docker.py` | 可选 Docker 隔离 | `SandboxDockerExecutor.run_shell/run_tests` |
| `governance/diff_preview.py` | diff 计算 + 预览 | `DiffPreviewer.preview()` |
| `governance/task_report.py` | 任务总结 | `TaskReport.build()` |

### 5.4 反馈层(★深做)
| 文件 | 职责 | 关键类型 |
|------|------|---------|
| `feedback/types.py` | 数据模型 | `FailureCategory` `TestFailure` `TestRunResult` `FailureReport` |
| `feedback/pytest_parser.py` | junit→结构化 | `parse_pytest_output()` |
| `feedback/classifier.py` | 失败分类 | `classify_failure()` `classify_run()` |
| `feedback/strategy.py` | 分类→hint | `strategy_hint()` |
| `feedback/stuck.py` | 卡住检测 | `StuckDetector.update()` `signature_of()` |
| `feedback/engine.py` | 串联→FailureReport | `FeedbackEngine.classify()` |

### 5.5 记忆/上下文层
| 文件 | 职责 | 关键类型 |
|------|------|---------|
| `context/manager.py` | 上下文组装(build_chat/build_initial/build) | `ContextManager` `locate_impl_module()` |
| `memory/compactor.py` | 对话压缩 | `Compactor.maybe_compact()` |
| `memory/retriever.py` | 符号/grep 检索 | `Retriever.symbols()` `Retriever.grep()` |
| `memory/store.py` | 跨会话 notes+log | `MemoryStore.load_notes()` `append_log()` |

### 5.6 LLM 抽象层
| 文件 | 职责 | 关键类型 |
|------|------|---------|
| `llm/base.py` | Protocol | `LLMClient.complete(messages) -> str` |
| `llm/mock.py` | 离线测试接缝 | `MockLLMClient(script)` |
| `llm/zhipu.py` | 真实 GLM-4.6 | `ZhipuLLMClient(model, api_key)` |

### 5.7 其他
| 文件 | 职责 |
|------|------|
| `config.py` | `Config` dataclass + `harness.toml` 加载 |
| `credentials.py` | `CredentialStore`: Fernet+PBKDF2 加密存储 |
| `types.py` | `Message(role, content)` 共享数据类 |
| `interactive/presenter.py` | REPL 渲染(纯文本,注入 stream) |

---

## 6. 配置参考(`harness.toml`)

```toml
[scope]
project_root = "."
allowed_write_dirs = ["src"]         # Guardrail scope fence

[guardrails]
dangerous_shell_patterns = [...]     # → AskHuman
network_commands = [...]             # → AskHuman
fail_closed_when_noninteractive = true

[budget]
max_iterations = 20                  # 单轮最多 LLM 调用数
max_parse_failures = 5               # 连续解析错误上限
stuck_repeat_n = 3                   # 同一失败签名重复 N 轮→STUCK
stuck_no_progress_m = 4             # 无进展 M 轮→STUCK
test_timeout_s = 30                  # 单次 run_tests 超时

[feedback]
hint_history_lines = 8               # traceback 摘录行数

[context]
max_history = 8                      # 保留最近 K 轮原文
compact_threshold = 6000             # 超→压缩
keep_recent = 6                      # 压缩后保留
mention_max_chars = 8000             # @mention 单文件上限
mention_max_files = 3               # @mention 文件数上限

[sandbox]
network = "allowlist"                # offline|allowlist|open
network_allow = []                   # allowlist 模式白名单
denied_commands = [...]              # 硬拒正则
write_roots = ["src"]                # FS 写范围
containerize = false                 # 可选 Docker 隔离
container_image = "python:3.11-slim"

[diff]
preview = "ask"                      # always|ask|never (chat 模式)
```

---

## 7. 扩展指南

### 7.1 加一个新工具(如 `grep_search`)

1. **`actions/protocol.py`**:加 `@dataclass(frozen=True) class GrepSearch(Action): pattern: str; path: str = "."`。
2. **`actions/parser.py`**:在 `_SIMPLE` 加 `"grep_search": lambda p: GrepSearch(p["PATTERN"], p.get("PATH", "."))`。
3. **`tools/dispatcher.py`**:加 `if isinstance(action, GrepSearch): ...` 分支,调 `Retriever.grep` 返回 `ToolResult`。
4. **`context/manager.py`**:系统提示 `_CHAT_SYSTEM` 加范例。
5. 测试:`test_actions_protocol` / `test_dispatcher` / 集成。

### 7.2 加一条治理规则

- **Guardrail 层(问人)**:`config.dangerous_shell_patterns` 加正则 → AskHuman。纯配置,不用改代码。
- **Sandbox 层(硬拒)**:`config.sandbox_denied_commands` 加正则 → Deny。纯配置。
- **新边界类型**:在 `Sandbox.check` 加分支 + Config 字段 + 测试。

### 7.3 接一个新 LLM 供应商

1. **`llm/<provider>.py`**:实现 `LLMClient.complete(messages) -> str`(调供应商 chat-completion,lazy-import)。
2. **`cli.py`**:`_resolve_llm` 加分支读对应 key。
3. 测试:gated `@pytest.mark.live`。

---

## 8. 测试策略(§A.4-C:mock/stub + 确定性 + 离线)

| 层 | 测试方式 | 文件 |
|----|---------|------|
| 纯函数(parser/classifier/strategy/stuck/diff/report/compactor/retriever) | canned 输入→断言输出 | `tests/unit/test_*.py` |
| 组件(dispatcher/guardrail/sandbox/hitl) | 构造 Action→断言决策 | `tests/unit/test_*.py` |
| 集成(ChatRunner/AgentRunner 全 loop) | MockLLMClient + 假输入 + Spy presenter + tmp_path fixture | `tests/integration/test_*.py` |
| 真实 LLM | `@pytest.mark.live`(默认 deselect,需 `ZHIPU_API_KEY`) | `tests/integration/test_zhipu_live.py` |
| Docker | mock subprocess→断言 argv | `tests/unit/test_sandbox_docker.py` |

**铁律**:默认 `make test`(`pytest -m "not live"`)零网络、零真实 LLM、确定性。234 测试。

---

## 9. 快速上手

```bash
# 安装(需 Python ≥ 3.11)
pip install -e ".[full,dev]"

# 配置凭据(§3.1)
harness init                          # 主密码 + GLM key(getpass 隐藏)

# 跑对话式 agent
export ZHIPU_API_KEY="<key>"
harness chat --repo examples/demo     # 自由对话
harness chat --repo .                 # 在本项目里干活

# 一次性任务(非交互)
harness task --repo examples/demo --goal "修复 add" --accept tests/test_foo.py::test_add

# 离线机制演示
make demo                             # ①护栏 ②反馈改动作 ③分类差异

# 测试
make test                             # 234 passed (offline)
make lint                             # ruff clean
```

---

## 10. 设计决策与取舍

| 决策 | 理由 |
|------|------|
| 文本协议(非 tool-calling) | provider 无关;只用单次 chat-completion(§A.4-A);mock 极简 |
| 反馈闭环做深 | 最客观的"正确性"信号(红→绿);最可编码;§A.6 展品 |
| 治理三层(Guardrail→Sandbox→DiffGate) | 分层防御;每层独立确定性代码;Guardrail 问人 / Sandbox 硬拒 / DiffGate 审查 |
| Compactor 结构化(非 LLM 摘要) | 确定性(§A.4-C);零成本;无额外 LLM 调用 |
| run_shell STDIN 支持 | 让 agent 驱动交互 CLI(高自由度,类 Codex) |
| write_file 接受 raw-after-PATH | LLM 写大文件不因块格式连错(高自由度) |
| Docker 可选(非强制) | A 代码边界为主(全平台 mock 可测);B 容器为升级(真隔离) |

---

## 11. 建议阅读顺序(由浅入深)

1. **跑起来**:`make demo` → `harness chat --repo examples/demo`。
2. **读主循环**:`interactive/chat.py::_agent_loop`(整个 turn 的逻辑,~70 行)。
3. **读协议**:`actions/protocol.py`(7 个 Action)+ `actions/parser.py`(文本→Action)。
4. **读反馈(深做)**:`feedback/engine.py` 串起 `pytest_parser→classifier→strategy→stuck`。
5. **读治理**:`guardrails/sandbox.py`(硬边界)+ `governance/diff_preview.py`(diff 审批)。
6. **读记忆**:`memory/compactor.py`(压缩)+ `memory/retriever.py`(检索)。
7. **读测试**:每模块都有 mock 单测——是最好的"行为说明书"。
8. **读过程**:`SPEC_PROCESS.md`(冷启动)+ `AGENT_LOG.md`(Critical 怎么被抓+修)。
