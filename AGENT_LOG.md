# AGENT_LOG.md

按时间顺序的关键节点记录（§4.9）。本会话发生于 2026-07-25（单日，连续）。
主智能体：OpenCode（glm-5.2）。冷启动验证智能体与各 task 实现均为**新鲜 subagent**（无共享上下文）。
commit hash 是持久证据；SDD ledger（task 级 brief/report/review）为 worktree 本地 scratch，分支合并后随 worktree 删除，故以 git 历史为准。

---

## Phase 0 — brainstorming → SPEC（技能：`brainstorming`）

- **节点**：用户问"下一步该做什么"。读 `docs/REQUIREMENTS.md`（= 通用 + A 拼接），确认项目为 A · Coding Agent Harness，零实现。
- **关键 prompt/决策**：brainstorming 技能一次一问，共 8 个分叉点 + 1 个架构分叉。**用户拍板**：① 深做维度=反馈闭环（我推荐，采纳）② 语言=Python ③ target=pytest ④ 招牌任务=TDD red-green ⑤ LLM=智谱 GLM ⑥ 凭据=主密码加密文件 ⑦ 分发=Docker+PyPI ⑧ 自修正=分类+策略+卡住 ⑨ 动作协议=结构化文本（非 tool-calling，§A.4-A）。
- **人工干预（重要）**：我初判 ContextManager 为"最低凑合"，**用户反驳"context 也很重要"** → 我提三档，用户选"工程化投递层"（选择/裁剪/强调/快照四机制，皆可单测），深度仍归反馈闭环。
- **§五.9 意外**：收尾核对交付清单时发现 §五.9 无条件规定 WebUI（CLI 项目也必须）。用户选"加薄 WebUI + 部署"。
- **产物**：`SPEC.md`（13 节，含 §A.5 领域机制设计）。commit `4840b94`。

## Phase 1 — writing-plans → PLAN（技能：`writing-plans`）

- **节点**：把 SPEC 拆成 23 个 TDD task（T0–T22），每个含文件路径 + Consumes/Produces 接口契约 + 红→绿→commit 步骤 + 真实代码。
- **自审**：发现并修一处类型一致性 bug（`FailureReport` 未在 T3 定义却跨 task 使用）。
- **产物**：`PLAN.md`（2593 行）。commit `1a9c093`。

## Phase 2 — §4.5 冷启动验证（最关键的客观证据）

- **设置**：派**全新 `general` subagent**（无对话历史），仅给 SPEC+PLAN，实现 T0+T3+T4。
- **结果**：代码 9/9 绿，但返回 **11 条 findings**。
- **关键发现**：
  - **F1（CRITICAL）**：解析器输出 `nodeid=classname.name`，而 harness 其余用 pytest `path::name` 选择器——永不匹配，task 边界不可见。
  - **F3（HIGH）**：`is_green` 丢了 SPEC 要求的 `exit_code==0`。
  - **F2/F6**：TIMEOUT 从 stderr 不可达；分类器精确串匹配遇带模块前缀的真名即失效。
- **子 agent 判词**：*"plan optimizes for local green over global correctness"*——一个忠实 TDD 的全新实现者会过每道门，却仍交付"反馈标识无人能消费"的反馈闭环。
- **修订**：SPEC/PLAN 全量回修（F1–F11），记入 `SPEC_PROCESS.md`（before/after diff）。commit `ed357e3`。验证代码留档于 `coldstart/t3-t4` 分支。
- **教训**：分节签字 ≠ 全局一致；跨节接口契约（命名空间）只有让无共享上下文的实现者真去接才会暴露。单人项目里这是最接近同侪评审的机制。

## Phase 3 — PR1 feedback-core（技能：`using-git-worktrees` → `subagent-driven-development` → `requesting-code-review` → `finishing-a-development-branch`）

worktree `.worktrees/feedback-core`（`feat/feedback-core`）。每 task：新鲜实现 subagent → 两阶段评审（spec+quality）→ 必要时 fix loop → ledger。

| task | commit | 评审 |
|------|--------|------|
| T0 bootstrap | `e12d37c` | controller 直做（纯脚手架，无逻辑） |
| T3 types+pytest 解析 | `67ada5a` | Approved（4 minor） |
| T4 分类器 | `8c778a1` + `759d9b7`(plan 文本 5→6) | Approved |
| T5 策略映射 | `d1e0a1b` | Approved |
| T6 卡住检测 | `33f6d7f` | Approved |
| T7 FeedbackEngine | `ab8711d` | Approved |

- **最终全分支评审**：With fixes（2 Important：ruff lint 红、`ET.fromstring` 未守 §3.6 parse-fail 契约）。
- **修复波** `c70740c..1ccc551`：全 addressed，0 新增 breakage，28/28 绿。
- **合入**：用户选"合回 main 本地"。fast-forward，删 worktree+分支。

## Phase 4 — PR2 governance（`feat/governance`：T1/T8/T9/T10/T11/T12）

- T1 `8c9897c`、T8 config `f160521`、T11 credentials `41bad7c`、T12 memory `d4d9b13`、T9 guardrail `f7f4f01`、T10 HITL `15743ee`。
- **T11 fix loop（1 轮）** `54ce698`：corrupt-JSON→CredentialError、0o600、kdf_iters 持久化（评审 Important）。
- **最终评审 With fixes**：3 Important（`cryptography` 不在 dev→CI 红、symlink 绕过围栏、`max_history` 被忽略）。
- **修复波** `91c5266`：+realpath 围栏、fail-closed 未知动作、网络命令词边界正则、O_NOFOLLOW、recent_log 容错……63/63 绿。
- **合入** main。

## Phase 5 — PR3 integration（`feat/pr3`：T2/T13/T14/T15/T16/T17 ★）

- T2 parser `fa2727a`+`3cf1940`(PATH-guard)、T13 runner `df2afc9`、T14 dispatcher `cc1f7f9`、T15 context `19935e5`、T16 llm-mock `a81bb38`、**T17 AgentRunner `fa39670`**。
- **T17 集成暴露两个"已合入 PR 的潜在 bug"**（commit `5f94c12`）：① pytest xunit2 `<testsuites>` 包装使旧解析器把真实失败读成绿；② 同秒编辑导致 stale `.pyc`。冷启动用手工 fixture 没包装层故漏检。
- **最终评审：NOT mergeable，2 Critical**（均被 mock 假绿掩盖）：
  - **C1**：真实 pytest `<failure>` 无 `type=` → 默认 UnknownError → 分类成 UNKNOWN（最常见case），深做维度塌陷。手工 fixture 用了 `type="AssertionError"` 故漏。
  - **C2**：工具观测（read_file/list_dir/run_shell 输出）只进 Turn.summary 展示，**从不回灌上下文** → 真实 LLM 下 agent 看不到自己读的文件，perceive→act 断环。mock 脚本观测无关 + build_initial 预注入 impl 故漏。
- **修复波（2 轮）**：`186e786`(C1 推断 exc_type)、`779ef92`(C2 回灌观测 + 新文件 diff)。**轮 2** `213d7f7`：C2 回归测试原本重言式（marker 经 build_initial 注入泄露）→ 改用独立 helper.py + `OBSERVATION:` 前缀断言，验证 red-without-fix。97/97 绿。
- **教训**：mock 驱动的集成测试会"假绿"——只有用 callable mock 检视观测消息，才能抓住观测回灌回归。这是本项目最深刻的工程教训。
- **合入** main。

## Phase 6 — PR4 real-llm+cli+demo（`feat/pr4`：T18/T19/T20）

- T18 zhipu `6a0f6bc`（lazy-import httpx，保默认套件离线收集）、T19 CLI `13db363`、T20 §A.6 demo `d68552d`。
- **T19 fix** `5c6bc68`：API key 改 getpass（§3.1，brief 原为 input 明文）。
- **最终评审 With fixes**：5 Important（lint 不含 scripts、demo ②断言不分歧、demo ③不锁 hint、测试 marker-only、`fix` 零覆盖）。
- **修复波** `85a81e9`：103/103 绿。
- **合入** main。

## Phase 7 — PR5 web+distribution（`feat/pr5`：T21/T22）

- T21 WebUI `d6301cc`、T22 Docker+CI `7828fc5`。
- **最终评审：NOT mergeable，又 2 Critical**：
  - **C1**：CI `unit-test` 用 `.[dev]` 装不上 fastapi，但 `test_webui.py` 顶部 import → 干净 runner 收集即红（本地因已装 fastapi 假绿）。
  - **C2**：§五.9 demo 终于 ERROR 而非 SUCCESS——两根因：OLD 块空格不匹配 + fixture 缺 conftest（pytest 收集 0 测试，永远不绿）；宽松断言 `or "RunTests"` 掩盖。
- **修复波** `5de9c02`：CI 改 `.[full,dev]` + apt 装 make、demo 空格对齐 + conftest + 收紧断言（实测达 SUCCESS）、Makefile 出 junit、filterwarnings、lint 含 web/、Finish 不再被分发。108/108 绿（`-W error` 0 警告）。
- **合入** main。**全部 23 task 实现完成。**

## Phase 8 — 范围纠偏:对话式 CLI（feat/chat）

- **节点**：用户要求把招牌任务从"TDD red-green 一次修一个失败"扩成"对话式编码 agent"（Claude/Codex 风格多轮 REPL + 一次性 `task` 模式）。经 `brainstorming` 技能厘清范围 → SPEC delta（commit `86c7b72`，追加 §五.10 interactive 包设计：`ChatRunner` 复用 AgentRunner 组件但自带 REPL 循环、`build_chat` 通用 chatty 提示、`Presenter` ANSI 渲染、`split_prose_and_action` 解析散文+动作）→ 6-task TDD 计划（T1 split_prose `7b0aed2`、T2 Presenter `dbff7e6`、T3 build_chat `8c44c7b`、T4 ChatRunner REPL `29a6553`、T5 cli `chat`/`task` 子命令 `688e36f`、T6 本条目 + examples/demo + README §Conversational REPL）→ 合入 main。**关键设计决策**：不动 `AgentRunner.run`（批处理循环保持原状、108 旧测绿 by construction），`ChatRunner` 独立循环（终止/呈现/approver 真有分歧才 justify divergence）；HITL 在危险/网络动作前 `y/N`，`--accept <selector>` 达绿自动收尾。
- **产物**：`src/harness/interactive/{presenter,chat,runner}.py` + cli `chat`/`task` 子命令 + `examples/demo/`（故意红样本，演示 `--accept` 自收尾）。

---

## 跨阶段人工干预汇总

1. 维度选型（采纳推荐：反馈闭环）。
2. Context 升级（用户主导推翻我的"最低"框架）。
3. WebUI 加入（§五.9 强制）。
4. 每个 PR 整合方式：均"合回 main 本地"。

## 跨阶段教训（沉淀）

- **"local green ≠ global correct"** 是贯穿全项目的母题：冷启动、集成评审、PR5 评审各暴露一层 task 边界不可见的缺陷。
- **mock 假绿**：mock 驱动的测试最危险——它让你以为闭环通了。callable mock 检视观测是抓住"回灌断环"的唯一手段。
- **brief 自相矛盾**：plan 的 prose 与 code/test 多处不一致（正则空格、测试计数、fixture 空格、缺 conftest）。实现者遵循 TDD 契约（test 为准）是对的；plan 文本应回修（少数已修，T2/T15 文本待补）。
- **subagent-driven + 两阶段评审**有效：23 task 仅靠"新鲜 subagent + 评审 + fix loop"推进，每 PR 的 Critical 都由评审（而非实现者自报）抓住。
- **Superpowers 七步是真脚手架**：brainstorming 逼问、writing-plans 接口契约、冷启动验证、subagent 隔离——每一步都产出了可验证的工程价值，而非形式。
