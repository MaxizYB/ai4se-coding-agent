# SPEC · Coding Agent Harness（TDD Red-Green Fixer）

> 依据：`docs/REQUIREMENTS.md`（= 通用要求 + A · Coding Agent Harness 拼接，单一事实来源）。
> 本 SPEC 由 `brainstorming` 技能沉淀，是后续 `PLAN.md` / 实现 / 评审的基准。
> 核心命题：**Agent = LLM + Harness**。LLM 只决定"下一步做什么"，其余全是工程——本 SPEC 描述我要自己编码的那台机器。

---

## 1. 问题陈述

### 1.1 要解决什么问题
把"只会产生下一步设想的 LLM"封装成一台**对话式通用编码 agent**(类 Claude / Codex / OpenCode 的 CLI):用户用自然语言下达任务("给 X 加个登录函数"/"修 Y 里的 bug"/"重构 Z"),harness 多轮交互、自由 read/write/edit/shell/run_tests 完成任务,**按测试结果自我修正**(§A.2),危险动作内联审批,完成自判停机。

这是对作业范围的纠偏:招牌任务**不再**是窄的"单测试 red-green 修复",而是通用编码 agent;red-green 修复保留为 `--accept <测试>` 的一种用法(给定验收测试 → 跑到绿)。内核(主循环/解析/工具/治理/HITL/反馈/上下文/记忆/凭据/配置)复用;深做维度(**反馈闭环**)不变——它正是 §A.2"据测试结果自我修正"的落点,现在在对话里随时可见(agent 选择跑测试时启动分类+纠错)。

交互外壳的设计细节见 `docs/superpowers/specs/2026-07-25-interactive-chat-cli-design.md`。

### 1.2 为什么这是 harness 问题而非 LLM 问题
- **决策封装、动作工具、上下文记忆、治理护栏、反馈闭环、配置** 六件事都必须是**我编写的确定性代码**，不是提示词。
- 移除真实 LLM（换 mock）后，harness 的每个核心机制仍能用确定性单测验证（§A.4-C 硬判据）——这才算"我实现了一个 harness"。

### 1.3 目标用户
- 个人开发者:在 CLI 里用自然语言驱动 agent 自由修改项目(增/改/纠错),像用 Claude Code / Codex 那样。
- TDD 开发者:写好失败测试后,`harness chat --accept <测试>` 让 agent 把实现补到绿。
- 本课程评审者:检验作者是否真的"编码了机制"而非"写了提示词"。

### 1.4 为什么值得做
它用最小、最可编码的形态逼出 harness 六维度的真实工程：反馈信号最客观（红→绿）、危险动作最具体（破坏性 shell）、记忆最自然（项目约定）。深度落在**反馈闭环**，直接对齐 §A.4-C 与 §A.6 机制演示。

---

## 2. 用户故事（INVEST）

- **US1 · 修复失败测试**：作为开发者，我给出仓库路径与一个失败测试选择器，harness 自主把它修到绿或给出结构化失败报告，以便我不用手写样板实现。
- **US2 · 安全录入 key**：作为用户，首次运行我用隐藏输入录主密码与 GLM key，此后查看只显 set/unset、可更新/清除，以便 key 不落明文、不进 git。
- **US3 · 拦截危险动作**：作为用户，当 agent 想执行破坏性 shell 或装包/联网时被暂停并问我（以便审批后才放行），而越界写被自动拒绝（不需我介入）。
- **US4 · 可观测的循环**：作为用户，我能看到每一轮的动作、护栏判定、测试结果与失败分类，以便理解 agent 为什么这么做。
- **US5 · 全新机器从零运行**：作为新用户，我单条 `docker run` 或 `pip install` 就能跑起来并安全配上自己的 key，以便零环境折腾。
- **US6 · 网页演示**（§五.9）：作为评审者，我打开公网 URL 提交任务、流式观看循环、看到终局与 diff，以便不装环境也能验收。
- **US7 · 对话式编码**（范围纠偏后招牌）：作为开发者，我在 CLI 里 `harness chat` 用自然语言驱动 agent——"修这个 bug"/"加这个功能"/"重构这块"——agent 自由读写文件、跑 shell、跑测试自检,危险动作当场问我,完成自判停下、我可继续追问;以便像用 Claude/Codex 那样自由改项目(含纠错)。

---

## 3. 功能规约（按模块）

> 每项给：输入 / 行为 / 输出 / 边界 / 错误处理。通用错误处理：任何子件抛错都被 `AgentRunner` 捕获、记入运行日志、按终止语义处理（不裸崩）。

### 3.1 `AgentRunner`（主循环编排）
- 输入：`Task{repo_path, test_selector, budget}`、`LLMClient`、`Config`、`Approver`。
- 行为：执行 §4.3 主循环；维护动作历史、失败签名序列；判定终止。
- 输出：`RunResult{outcome, turns[], edits_diff, failure_report}`。
- 终止状态：`SUCCESS`（绿）/ `STUCK`（卡住）/ `BUDGET_EXHAUSTED`（超迭代或解析失败上限）/ `HUMAN_ABORTED`（HITL 否决到不可继续）/ `ERROR`。
- 边界：`budget.max_iterations`、`budget.max_parse_failures`、`stuck_repeat_n`。
- 错误：子件异常 → 记日志 → 若不可恢复则 `ERROR`。

### 3.2 `LLMClient`（抽象层，§A.4-A）
- 接口：`complete(messages: list[Message]) -> str`。
- `MockLLMClient`：吃脚本（写死 raw 输出序列 / callable），按序返回；所有离线测试用之。
- `ZhipuLLMClient`：调智谱 GLM 单次 chat-completion；key 取自 `CredentialStore`；只返回原始文本。
- 边界：LLM 永不结构化动作——动作化是 `ActionParser` 的职责。
- 错误：网络/限流 → 重试退避 N 次 → 仍败则该轮按 `ERROR` 终止。

### 3.3 `ActionParser`（文本协议 → Action，纯函数）
- 输入：LLM 原始文本。
- 行为：定位首个 `ACTION:` 起贪心读到块结束或下一个 `ACTION:`；解析 `KEY: VALUE` 参数行与配对 `<<<TAG … >>>TAG` 内容块；返回类型化 `Action`。
- 输出：`Action` 子类实例。
- 边界：容错忽略周边自然语言；标签不配对/缺参数 → `ParseError(reason)`。
- 错误：`ParseError` 回灌"上一条非合法动作：<原因>，每轮只输出一个动作"，计入 `max_parse_failures`；连续超限 → `ERROR`。

### 3.4 `ToolDispatcher`（动作执行）
- 动作集：`read_file` / `list_dir` / `write_file` / `edit_file`（OLD→NEW 块替换）/ `run_shell`（治理）/ `run_tests`（输出送 `FeedbackEngine`）/ `finish`。
- 输出：`ToolResult{ok, stdout, stderr, exit_code, junit_xml?}`。
- 边界：路径必须在 `scope.allowed_write_dirs`；`run_tests` 仅跑配置命令，带 `budget.test_timeout_s`；`edit_file` 的 OLD 块未匹配 → `ToolResult.ok=false` 回灌原因（供 agent 校正）。
- 错误：执行异常 → `ToolResult.ok=false`，原文回灌。

### 3.5 `Guardrail` + `HITL`（治理，最低）
- `Guardrail.check(action) -> Allow | Deny(reason) | AskHuman(reason)`，规则配置驱动（见 §3.8）：范围围栏、危险 shell 正则、网络/装包命令。
- `HITL`：`submit(action)->request_id`、`resolve(id, decision)`；"等人类"由注入 `Approver`（`ConsoleApprover` / `StubApprover`）承担；非交互 + `fail_closed_when_noninteractive` → 任何 `AskHuman` 自动 `Deny`。
- 边界：`Deny`/`AskHuman` 结果回灌 LLM。
- 错误：审批超时 → 按配置 fail-closed 或 `HUMAN_ABORTED`。

### 3.6 `FeedbackEngine`（★ 深做，见 §11）
- 输入：`run_tests` 的 `ToolResult`。
- 行为：`PytestOutputParser`（junit XML 主、stderr 兜底）→ `FailureClassifier`（ENV/LOGIC/TIMEOUT/UNKNOWN）→ `StrategyMap`（类→hint）→ `StuckDetector`（签名重复/无进展）。
- 输出：`FailureReport{is_green, category, failing[], hint, traceback_excerpt, expected, actual, signature, stuck}`。
- 边界：`is_green` 判定 = `failed==0 && errors==0 && exit_code==0`；`stuck` 触发 `STUCK`。
- 错误：XML 缺失/解析败 → 从 stderr 抽 exc_type 造伪 failure，归类 `UNKNOWN`。

### 3.7 `ContextManager`（工程化投递层）
- 行为：每轮组装有界 prompt——系统提示（角色+协议+约束+scope）+ memory 笔记 + 相关文件（沿测试 import 静态定位被测模块）+ 动作历史（裁到最近 K 轮摘要）+ 上轮 `FailureReport`（hint 置顶强调）+ 当前文件真实快照。
- 输出：`list[Message]`。
- 边界：超预算按"丢最旧历史、保留首轮目标与全部 feedback"规则裁剪；断言裁后仍含 feedback、不超限。
- 错误：定位不到被测模块 → 仅含测试源码，回灌提示 agent 自行 `list_dir` 探查。

### 3.8 `Config`（声明式规则）
- 来源：`harness.toml`。
- 字段：`scope.project_root`、`scope.allowed_write_dirs`、`guardrails.dangerous_shell_patterns`、`guardrails.network_commands`、`guardrails.fail_closed_when_noninteractive`、`budget.{max_iterations,max_parse_failures,stuck_repeat_n,stuck_no_progress_m,test_timeout_s}`、`feedback.hint_history_lines`、`context.max_history`。
- 行为：加载 + 校验（缺字段给默认；非法值报错）。
- 错误：文件不存在 → 用安全默认并提示；非法 → 拒绝启动。

### 3.9 `CredentialStore`（凭据，§3.1）
- 见 §12。

### 3.10 薄 WebUI（§五.9）
- FastAPI：表单（仓库/测试选择器/预算）→ 后台跑 `AgentRunner` → SSE 流式推送每轮（动作/护栏判定/测试结果/失败类+hint）→ 终局 + edits diff；交互模式下 HITL 在 UI 弹审批。
- 边界：纯展示层，不含 harness 逻辑；非交互（演示/CI）fail-closed。

### 3.11 `ChatRunner`（对话式 REPL，范围纠偏后招牌，详见 design delta）
- `harness chat [--repo PATH] [--accept TEST]`：多轮交互 REPL。用户自然语言输入(或 `/help`/`/exit`/`/clear`/`/tests`/`/status`)→ agent 内层循环(每轮 LLM 先述后做、抽 ACTION、治理拦截、执行、run_tests 时触发 FeedbackEngine 分类+纠错)→ Finish/预算/`--accept` 绿 即停回提示符。
- `harness task "<目标>" [--accept TEST]`：同一引擎非交互(一次性)版,FaliClosedApprover。
- 行为:agent 自由 read/write/edit/shell/run_tests(由 LLM 决定);HITL 用 `ConsoleApprover`(内联 y/N);Presenter(`cli/presenter.py`)显示 prose/动作/结果/反馈分类。
- 终止策略:`ChatPolicy`(Finish/预算/--accept 绿)与 `FixPolicy`(绿/卡住/预算)共用 `AgentRunner.step()`。
- 边界:复用内核全部组件;本轮不做 token 流式与跨会话 /resume。
- 错误:ParseError 回灌(连续超限→ERROR);子件异常记日志。

### 3.12 `Sandbox`（执行级硬沙箱，治理深做）
- `src/harness/guardrails/sandbox.py`。在 Guardrail(问人)之上、dispatcher 执行之前，强制**硬边界**(无论如何不许的层)。
- 三条边界(全配置驱动、确定性、mock 可单测):
  - **命令 denylist**：`sandbox.denied_commands` 正则 → `Deny`（不问不跑）。默认：`rm -rf /`/`mkfs`/`dd of=`/fork bomb/`sudo`。
  - **网络 egress**：`sandbox.network` ∈ `offline`/`allowlist`/`open`（默认 `allowlist`）。命中网络工具集(`curl`/`wget`/`pip install`/`git push`…)且不在 `network_allow` 白名单 → `offline` 硬拒 / `allowlist` 问人。
  - **FS 写范围**：`sandbox.write_roots`（默认 `["src"]`），用 `os.path.realpath` 防 symlink 绕过，越界写硬拒。
- `Sandbox.check(action) -> Allow | Deny | AskHuman | Containerize`。
- 可选 `Containerize` → `SandboxDockerExecutor`（§3.13）：`sandbox.containerize=true` 时，命令在 `docker run --rm --network=none --read-only --tmpfs /tmp -v <repo>:/work` 里跑（真隔离）。
- 与 Guardrail 的关系：Guardrail 管"问人"(scope fence + AskHuman)；Sandbox 管"无论如何不许"(denylist 硬拒 + 禁网 + write_roots)。三层防御：Guardrail → Sandbox → DiffGate。

### 3.13 `SandboxDockerExecutor`（可选容器隔离）
- `src/harness/guardrails/sandbox_docker.py`。`Sandbox.check` 返回 `Containerize` 时，由它替代 `ToolDispatcher` 执行。
- `docker run --rm --network=none --read-only --tmpfs /tmp -v <repo>:/work -w /work <image> sh -c <cmd>`。禁网、系统只读、仅仓库可写。
- 接口可注入 fake runner（mock 测 argv），真实 docker = opt-in 集成测。默认关。

### 3.14 `DiffPreviewer` + `DiffGate`（写前预览审批，治理深做）
- `src/harness/governance/diff_preview.py`。对 `WriteFile`/`EditFile` 在执行前计算 `difflib.unified_diff`，展示给用户审批。
- `DiffPreviewer.preview(action, project_root) -> (path, unified_diff)`（纯函数）。
- DiffGate(在 agent/chat 循环里，dispatcher 之外)：`config.diff_preview` = `ask`(交互审批)/`always`(展示后直接写)/`never`(静默)。批处理默认 `never`（避免 FailClosed 阻塞所有写）。
- 非交互 + `ask` → fail-closed（不写）。

### 3.15 `TaskReport`（结构化任务总结，治理深做）
- `src/harness/governance/task_report.py`。agent/chat 循环维护 `task_events` 列表（file_changed/shell/test），终止时 `TaskReport.build(task_events, outcome, summary)` → `{outcome, files_changed, commands_run, tests[], summary}`。
- `presenter.show_report` 渲染为用户可读的报告块。REPLIED（纯对话）+ 无事件时不显示报告。

### 3.16 `Compactor`（对话压缩，记忆深做）
- `src/harness/memory/compactor.py`。当历史 token 超 `context.compact_threshold`（默认 6000 chars），把旧轮压成一条 `[compacted history]` 结构化事实 system 消息（无 LLM，确定性），保留最近 `keep_recent`（默认 6）轮原文。
- 每轮事实 = action 类型 + 路径 + 结果（从 turns 提取，非 AI 摘要）。纯函数，mock 可单测。
- `ContextManager.build_chat` 在组装前调 `Compactor.maybe_compact(history)`。

### 3.17 `Retriever` + `@mention` + AGENTS.md（按需检索 + 文件注入，记忆深做）
- `src/harness/memory/retriever.py`：自实现符号索引（`ast` 扫 `.py` → `{name: [file:line]}`）+ grep（`re` 正则扫文件）。stdlib only，无框架（§A.4-D）。
- `@mention`：`ContextManager.build_chat` 解析用户消息中 `@<path>` → 读文件内容注入上下文（`realpath` + `commonpath` 防遍历，bounded `mention_max_chars`）。
- AGENTS.md：`build_chat` 自动载入 `<repo>/AGENTS.md`（标准项目记忆，类 CLAUDE.md）。

---

## 4. 系统架构

### 4.1 组件图
```
                       ┌─────────────┐
   Task ─────────────▶ │ AgentRunner │ ◀──── Config / CredentialStore
                       └─────┬───────┘
        ┌──────────┬──────────┼──────────┬───────────┐
        ▼          ▼          ▼          ▼           ▼
 ContextManager LLMClient ActionParser Guardrail  ToolDispatcher
   (memory)      (mock/     (文本协议) (+HITL)     (read/write/
                  zhipu)                             edit/shell/
                                                     run_tests)
                                                       │
                                              run_tests 输出
                                                       ▼
                                                FeedbackEngine ★
                                        (parser→classify→strategy→stuck)
                                                       │
                                              FailureReport 回灌
                                                       │
                                                       ▼
                                              ContextManager（下一轮）
```

### 4.2 数据流
用户任务 → `ContextManager.build` → `LLMClient.complete` → `ActionParser.parse` → `Guardrail.check`（→ `HITL` 审批）→ `ToolDispatcher.execute` →（若 `run_tests`）`FeedbackEngine` → `FailureReport` 回灌 `ContextManager` → …… → 终止 → `RunResult`。

### 4.3 主循环（伪码）
```
ctx = ContextManager.build_initial(memory, relevant_files)
while not terminated:
    raw    = LLMClient.complete(ctx)                 # 抽象、可 mock
    action = ActionParser.parse(raw)                 # 纯函数
    decision = Guardrail.check(action)               # 代码护栏
        if AskHuman: decision = HITL.resolve(...)    # 状态机
    if Allow:
        result = ToolDispatcher.execute(action)
        if action is run_tests:
            fb = FeedbackEngine.classify(result)     # ★ 深做
            if fb.is_green: terminated = SUCCESS
            elif fb.stuck:      terminated = STUCK
    ctx = ContextManager.build(history, fb)          # 回灌
    terminated |= budget_exceeded()
```

### 4.4 外部依赖
- LLM：智谱 GLM（chat-completion）。
- 被测 target：Python + pytest（深度解析）；测试命令可配置作 generic 退路。
- 库：`cryptography`（Fernet/PBKDF2）、FastAPI/uvicorn（WebUI）、`pytest`、标准库 `subprocess/xml/ tomllib`。

---

## 5. 数据模型

| 实体 | 关键字段 | 约束 |
|------|----------|------|
| `Message` | role, content | role∈{system,user,assistant} |
| `Action`（抽象） | type, … | 子类：ReadFile/ListDir/WriteFile/EditFile/RunShell/RunTests/Finish |
| `ToolResult` | ok, stdout, stderr, exit_code, junit_xml | — |
| `TestRunResult` | total, passed, failed, errors, failures[] | is_green 派生 |
| `TestFailure` | nodeid, exc_type, message, traceback | — |
| `FailureCategory` | ENV/LOGIC/TIMEOUT/UNKNOWN | 枚举 |
| `FailureReport` | is_green, category, failing[], hint, traceback_excerpt, expected, actual, signature, stuck | signature=frozenset((nodeid,category)) 的 hash |
| `Decision` | Allow/Deny/AskHuman + reason | — |
| `ApprovalRequest` | id, action, reason, state | state∈{PENDING,APPROVED,DENIED} |
| `RunResult` | outcome, turns[], edits_diff, failure_report | outcome∈{SUCCESS,STUCK,BUDGET_EXHAUSTED,HUMAN_ABORTED,ERROR} |
| `Config` | 见 §3.8 | 缺省安全默认 |
| `CredentialRecord` | provider, key_ciphertext, salt, kdf_iters | 明文永不落盘 |

---

## 6. 非功能性需求

- **性能**：单次 run_tests 受 `test_timeout_s` 约束；默认 `max_iterations=20`；mock-LLM 全套单测秒级。
- **安全（含凭据威胁模型）**：见 §12.3。
- **可用性**：CLI（`harness init/key/fix`）+ WebUI；first-run 引导。
- **可观测性**：每轮结构化日志 + JSONL 运行日志（task/outcome/关键动作/失败类）。
- **确定性/可测**：默认 CI 全离线、mock-LLM 驱动；真实 LLM 仅 gated live 测试。
- **可移植**：Linux/macOS/Windows；Python 3.11+；Docker 镜像与 PyPI 包。

---

## 7. 凭据与分发设计

### 7.1 凭据（详见 §12）
主密码加密文件为安全存储主方案；`.env` 为 dev 便利来源（标明文风险）；容器走 env。first-run 引导、查看不回显、可更新/清除。

### 7.2 分发
- **Docker（主）**：`Dockerfile`（python-slim + `harness`）→ `docker run -e ZHIPU_API_KEY=... -v $(pwd):/work harness fix --test ...`；CI 构建+push 公开 registry。
- **PyPI（辅）**：`pyproject.toml` + console script `harness`；`pip install <pkg>`。
- README 写清：获取、运行、key 安全配置（容器 env / 宿主加密文件）、已知限制（平台/Python 版本/需装被测项目依赖）。

---

## 8. 技术选型与理由

| 选择 | 理由 |
|------|------|
| Python | subprocess+XML 解析+失败分类最顺手；pytest 既是工具又是确定性靶子；keyring/PyPI/Docker 成熟；迭代快、契合"深度优先"。 |
| target = Python/pytest | 反馈信号最客观、junit XML 确定性可解析；可 dogfood。 |
| 智谱 GLM | 已有 key、国内稳定、免费额度够开发；抽象层可换。 |
| 结构化文本协议（非 tool-calling） | provider 无关、只用最底层 chat-completion（贴合 §A.4-A）；mock-LLM 极简；解析器本身是可单测机制（§A.4-C）。 |
| Fernet 加密文件 | 全平台可跑（无 daemon）、自实现、确定性可测；容器用 env 退路。 |
| Docker + PyPI | 全新机故事最强 + `pip install` 低成本辅。 |
| FastAPI 薄 WebUI | 满足 §五.9 MUST；纯展示层不稀释内核深度。 |

> 前端：加 WebUI 触发 §3.6 "前端推荐 Open Design"。本项目 WebUI 为极简演示面（流式日志 + HITL 弹窗），采用轻量自写前端（Jinja2 模板 + 少量原生 JS/SSE），在 SPEC 说明此选型；Open Design 留作可选增强，不作为必需。

---

## 9. 验收标准

- **Red-green MVP**：fixture 仓 1 个失败测试，mock-LLM 下**确定性**到达 `SUCCESS`（集成测试断言）。
- **反馈深做**：canned ENV/LOGIC/TIMEOUT/UNKNOWN 分类全对；`StrategyMap` hint 正确；重复签名/无进展 → `STUCK`（单测断言）。
- **治理**：canned 危险 shell→`AskHuman`(Guardrail)、硬拒 denylist→`Deny`(Sandbox)、越界写→`Deny`、symlink 绕过→`Deny`；非交互 fail-closed（单测断言）。
- **治理深做 — Sandbox**：网络 `offline` 硬拒 `curl`；`allowlist` 问人；`write_roots` 防 `realpath` symlink；`Containerize` mock 测 argv（`--network=none`/`--read-only`）；fail-closed when no executor。
- **治理深做 — DiffPreview**：`WriteFile`/`EditFile` 前 unified diff 计算（单测断言）；`StubApprover(True)` 放行 / `(False)` 跳过（集成测）。
- **治理深做 — TaskReport**：feed canned events → 断言 files_changed 去重 + tests green/red + summary（单测）。
- **记忆深做 — Compactor**：超阈值→1 条 system 摘要 + 保留 recent K（单测）；结构化事实含 action 类型（非 LLM 摘要）。
- **记忆深做 — Retriever**：fixture 仓 `symbols()` 含 `add@src/foo.py`；`grep("assert")` 命中（单测）。
- **记忆深做 — @mention**：`@src/foo.py`→内容注入；`@../../etc/passwd`→遍历防御拒绝（单测）。
- **机制演示**（§A.6）：`scripts/mechanism_demo.py` 离线确定性复现 ①护栏拦截 ②注入失败→反馈改动作 ③深做维度逐类不同行为，退出码 0。
- **凭据**：加解密 roundtrip；错主密码拒绝；磁盘无明文（`grep` 断言）。
- **分发**：全新机 `docker build && docker run` 与 `pip install` 均可跑。
- **WebUI**：提交→流式→终局+diff，公网 URL 可访问。
- **CI**：GitHub Actions `.github/workflows/ci.yml` 的 `unit-test` job 绿 + wheel 构建；默认 pipeline 最后一次 pass（[Actions](https://github.com/MaxizYB/ai4se-coding-agent/actions)）。
- **分发**：[GitHub Release v1.0.0](https://github.com/MaxizYB/ai4se-coding-agent/releases/tag/v1.0.0)（wheel + sdist）；`docker build && docker run` 与 `pip install` 均可跑。
- **离线可测**：默认测试集无网、mock-LLM 驱动整条 `AgentRunner`。
- **对话式 REPL**（范围纠偏后招牌）：`harness chat` 在 mock-LLM + 假输入流下确定性走完 用户消息→(read/edit/run_tests/…→)Finish 往返;HITL `y` 放行/`n` 拦截;`/exit` `/clear` `/tests` 生效;`--accept` 绿即停。`AgentRunner.step()`、`ChatRunner`、Presenter、`split_prose_and_action` 均有 mock 单测(§A.4-C 不退化)。

---

## 10. 风险与未决问题

- **R1 · CI 平台**：§五.6 原文写 `.gitlab-ci.yml`，助教确认用 **GitHub**。已替换为 `.github/workflows/ci.yml`（含 `unit-test` job + wheel 构建），`.gitlab-ci.yml` 已删除。
- **R2 · WebUI scope 蔓延**：严守"纯展示层"，harness 逻辑只在库/CLI；时间盒控制。
- **R3 · mock-LLM 不保证真实 GLM 守协议**：tolerant `ActionParser` + 解析失败回灌 + 一个 gated `@pytest.mark.live` 测试兜底。
- **R4 · pytest 输出漂移**：用 junit XML（稳定）而非扒文本，已规避；仍保留 stderr 兜底。
- **R5 · 容器 key 明文（env）**：README 标风险，建议生产用 secret mount；加密文件方案给非容器用法。
- **R6 · 主密码遗忘**：无后门、不可恢复——first-run 明示，文档强调。
- **R7 · Open Design 取舍**：当前定极简自写前端；若评审强调前端规范度，再切 Open Design（未决，低优）。
- **U1（已决）**：`run_tests` 是否允许 agent 自改测试文件——当前 `scope.allowed_write_dirs` / `sandbox.write_roots` = `["src"]`，测试目录只读，防 agent 改测试"作弊"。
- **R8 · mock 假绿（最重要的教训）**：234 个 mock-LLM 测试全绿，但真实 GLM 首次运行暴露 5 个 bug（write_file 格式、list_dir PATH、junit 相对路径、Finish 分发、对话轮次）；评审还发现 @mention 路径遍历、batch 模式 diff_preview 阻塞。**mock 测的是"agent 遵守协议"，不是"真实 LLM 遵守协议"**。已补充 live 冒烟测试 + 真模型端到端验证缓解，但这是 mock 驱动 TDD 的固有局限。

---

## 11. 领域与机制设计（§A.5 额外节）

> 回答 A 文件要求的四类机制 + 重点维度选择。

### 11.1 动作 / 工具
read_file / list_dir / write_file / edit_file / run_shell（治理）/ run_tests（输出送反馈）/ finish。`run_tests` 独立于 `run_shell`，唯有它触达 `FeedbackEngine`——这是反馈闭环的入口契约。

### 11.2 客观反馈信号（重点维度）
- **信号源**：`pytest --junitxml`（结构化、确定）+ exit code + stderr。
- **校验器/传感器（我写的代码，非提示词）**：`PytestOutputParser` → `FailureClassifier`（ENV/LOGIC/TIMEOUT/UNKNOWN，规则匹配 traceback 异常类型）→ `StrategyMap`（类→确定性 hint）→ `StuckDetector`（签名重复 N 轮 / 无进展 M 轮）。
- **回灌**：`FailureReport` 经 `ContextManager` 置顶强调注入下一轮。
- **为什么把反馈做深**：它天然由代码构成、最契合 §A.4-C"换 mock 仍可确定性单测"，且是 §A.6 机制演示②的中心展品。

### 11.3 危险动作
**三层防御**（均为代码，非提示词）：
- **Guardrail**（§3.5）：范围围栏 + 危险 shell 正则 + 网络/装包命令 → `AskHuman`（交 `HITL` 状态机）；非交互 fail-closed。
- **Sandbox**（§3.12）：命令 denylist → 硬拒 `Deny`（不问人）；网络 egress `offline`/`allowlist` 控制；FS write_roots 用 `realpath` 防 symlink 绕过。
- **DiffGate**（§3.14）：write/edit 前 unified diff + HITL 审批；批处理 fail-closed 不阻塞。

### 11.4 记忆
**自实现（§A.4-D），不接框架 memory：**
- `MemoryStore`（§3.8）：项目笔记（`HARNESS.md`，载入上下文）+ JSONL 运行日志（跨会话回放最近一条）。
- `Compactor`（§3.16）：长对话超阈值→结构化摘要旧轮（无 LLM，确定性），保留最近 K 轮。防上下文窗口爆炸。
- `Retriever`（§3.17）：stdlib `ast` 符号索引 + `re` grep 检索（按需定位，不全量载入）。
- `@mention`（§3.17）：用户消息 `@path` → 文件内容注入上下文（`realpath` 防遍历，bounded）。
- AGENTS.md 自动载入（§3.17）：标准项目记忆约定。

### 11.5 重点维度与理由
**三个深做维度**（§A.4-D 要求"选一个深做"，本项目超额完成三个）：

1. **反馈闭环（主要贡献）**：taxonomy + 策略映射 + 卡住检测的机制密度。是 §A.2"据测试结果自我修正"的落点，§A.6 机制演示②的中心展品。`ContextManager` 工程化投递层（选择/裁剪/强调/快照）保障反馈有效投递。
2. **治理（第二深做）**：从 Guardrail(问人) 升级为三层防御——Sandbox(硬沙箱：denylist + 网络控制 + write_roots + 可选 Docker 真隔离) + DiffGate(写前 diff 审批) + TaskReport(结构化总结)。§A.4-D 点名"沙箱"。
3. **记忆/上下文（第三深做）**：Compactor(结构化压缩，无 LLM，确定性) + Retriever(ast 符号索引 + grep，自实现) + @mention(按需拉文件) + AGENTS.md(项目记忆)。§A.3"按需提供给 LLM 而非全量载入"。

三个维度均为**确定性代码机制**，换 mock LLM 后仍可单测（§A.4-C）。

### 11.6 机制如何编码（呼应 §A.4）
- 反馈信号 = `FeedbackEngine`（解析→客观判定→回灌），确定性单测。
- 危险拦截 = 三层防御：`Guardrail(action)` 问人 + `Sandbox(action)` 硬拒 + `DiffGate` 写前审批，传入构造动作即断言，无需 LLM。
- 治理报告 = `TaskReport.build(task_events)`，feed canned events 断言。
- 记忆压缩 = `Compactor.maybe_compact(history)`，超阈值→结构化摘要，纯函数。
- 记忆检索 = `Retriever.symbols(root)` / `Retriever.grep(pattern, root)`，stdlib ast/re。
- 工具分发 / 治理 / 反馈回灌 / 记忆读写 / 停机，均换 mock LLM 后可单测。234 测试全离线。

---

## 12. 凭据威胁模型与流程（§3.1 详）

### 12.1 存储
`~/.harness/credentials.enc`：`cryptography.fernet`，密钥由主密码 + 随机 salt 经 PBKDF2（≥200k 迭代）派生，salt + kdf_iters 存文件头。明文永不落盘。

### 12.2 流程
- `harness init`：`getpass` 录主密码（二次确认）→ 录 GLM key（隐藏）→ 加密写入。
- `harness key status`：显 `set|unset`，不回显。
- `harness key set`：主密码 + 新 key 更新。
- `harness key clear`：删文件。
- 运行时：主密码优先取 `HARNESS_MASTER_PASSWORD`（不进 shell history）或交互 `getpass`；解密仅内存取用，不进日志。
- `.env`：支持 `ZHIPU_API_KEY`（dev 便利，标明文风险）；容器/CI 用此路径。

### 12.3 威胁模型与对策
| 威胁 | 对策 |
|------|------|
| `.env`/进程环境明文可见 | 仅 dev/容器便利；文档明示风险；生产建议 secret mount |
| 主密码被爆破 | PBKDF2 ≥200k 迭代 + 随机 salt 抗离线爆破 |
| 主密码遗忘 | 无后门、不可恢复——first-run 明示 |
| key 进 git/history/日志 | `.gitignore` 加密文件与 `.env`；不 `export`；不打印 key |
| 错主密码/篡改 | HMAC 校验失败即拒绝（单测覆盖） |

---

## 13. 与 Superpowers 工作流的对齐
本 SPEC 由 `brainstorming` 沉淀。下一步 `writing-plans` 拆 task → `using-git-worktrees` 隔离 → `subagent-driven-development` + `test-driven-development`（红绿重构）实现 → `requesting-code-review` → `finishing-a-development-branch`。过程证据入 `AGENT_LOG.md`；冷启动验证（§4.5）入 `SPEC_PROCESS.md`。
