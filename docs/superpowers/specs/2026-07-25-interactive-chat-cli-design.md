# Design Delta — Interactive Chat CLI (Claude/Codex-style)

> 在已实现的 harness 内核之上,加一层交互外壳,使其成为对话式通用编码 agent(类 Claude / Codex / OpenCode 的 CLI)。 brainstorming 产出,2026-07-25。
> 范围纠偏:招牌任务从"单测试 red-green 修复"扩为"对话式自由修改 + 测试自纠";red-green 修复保留为 `--accept <测试>` 的一种用法。
> 内核(主循环/解析/工具/治理/HITL/反馈/上下文/记忆/凭据/配置)**复用,不动**;深做维度(反馈闭环)不变。

---

## 1. 目标与非目标

**目标**
- `harness chat [--repo PATH] [--accept TEST]`:多轮交互 REPL,用户给自然语言任务,agent 自由 read/write/edit/shell/run_tests 完成,每轮"先述后做",危险动作内联审批,完成自判停机。
- `harness task "<目标>" [--accept TEST]`:同一引擎的非交互(一次性)版,FailClosedApprover。
- 像 Claude/Codex 的观感:看得见 agent 的发言、动作、测试分类与 hint。

**非目标(本轮不做)**
- token 级流式(需流式 API+SSE 解析,重;本轮用 turn-by-turn)。
- textual/rich 全功能 TUI。
- 跨会话 `/resume`(memory 已持久,但 REPL 历史不持久化)。

## 2. 架构(实现路径 B)

**重构 `AgentRunner` 为 step-wise + 终止策略**:
```
step(ctx) -> Turn + Termination{should_stop, reason}
```
`run()`(批处理,`fix` 用)与 `ChatRunner`(交互)共用 step,只换:
- **终止策略**:`FixPolicy`(绿/卡住/预算)vs `ChatPolicy`(Finish/预算;`--accept` 绿即成功)。
- **Approver**:`FailClosedApprover`(非交互)vs `ConsoleApprover`(交互 y/N)。

**新 `ChatRunner`(`cli/chat.py`)** 驱动 REPL + 注入 `Presenter`。

## 3. REPL 主循环

```
load memory + 项目笔记;presenter.welcome()
loop(外层,等用户输入):
  line = read_user()               # 读一行;空行跳过
  if line 是 /命令: handle_slash(); continue
  ctx.append(user(line))
  inner agent loop(chat policy):
    raw = LLM.complete(ctx)
    prose, action = split_prose_and_action(raw)   # ActionParser 照旧抽 ACTION;prose=动作前文本
    presenter.show_prose(prose)
    decision = guardrail.check(action)
    if AskHuman: decision = hitl.request(action, reason)   # ConsoleApprover 内联 y/N
    if Allow:
        result = dispatcher.execute(action)
        presenter.show_action(action, result)
        if isinstance(action, RunTests):
            fb = feedback_engine.classify(result)
            presenter.show_feedback(fb)            # 深做维度:分类+hint 在 REPL 可见
            if accept_test and fb.is_green: stop=SUCCESS
        ctx.append(user(observation + 反馈))
    if isinstance(action, Finish): presenter.show_done(reason); stop=FINISH
    if budget_exhausted: stop=BUDGET
    ctx.append(assistant(raw))
  end(inner)
  presenter.show_turn_end(outcome)
end(outer)
```

`split_prose_and_action`:`ActionParser.parse` 已容错忽略周边文本;新增辅助返回 `(动作前的文本, Action)`,动作前文本即 agent "发言"。无 ACTION → 整段视为纯发言(回灌,继续轮)。

## 4. ContextManager 泛化(新 `build_chat`)

- 系统:**"你是 `<repo>` 的编码 agent。完成用户任务;每轮先简述、再 emit 一个 ACTION;工具:read_file/list_dir/write_file/edit_file/run_shell/run_tests/finish;改完用 run_tests 自检;完成 emit finish。"** 若 `--accept <测试>`:补"验收:`<测试>` 绿即成功"。
- 不预注入失败测试/impl(agent 自行探索);载入 memory 笔记 + 对话历史。
- 历史有界(保留最近 K 轮,丢最旧,保留系统 + 反馈)。

## 5. Presenter(`cli/presenter.py`,纯 ANSI)

| 方法 | 显示 |
|------|------|
| `welcome()` | 项目路径 + 配置摘要 + `/help` 提示 |
| `show_prose(text)` | agent 发言 |
| `show_action(action, result)` | `✎ edit_file src/foo.py` + 紧凑结果;`read_file` 显示行数摘要;`run_tests` 显示 PASS/FAIL |
| `show_feedback(fb)` | 失败分类 + hint(深做维度可见) |
| `show_deny(reason)` | `✗ denied: reason` |
| `ask_human(action, reason) -> bool` | 内联 `[y/N]` |
| `show_done(reason)` / `show_turn_end(outcome)` | `✓ done` / `— outcome` |

## 6. 斜杠命令

`/help`(协议+命令清单)· `/exit`(或 Ctrl-D)· `/clear`(重置对话上下文)· `/tests [selector]`(立即跑测试+分类)· `/status`(配置/已用预算/memory)。

## 7. 终止与 HITL

- chat:`ConsoleApprover`(内联 y/N);task:FailClosed。
- 停机:`Finish`(agent 自判)/ 预算 / `--accept` 绿(=SUCCESS)。

## 8. 测试策略(§A.4-C:全离线 mock)

- `AgentRunner.step()` 重构:mock LLM 单测,验证 `Turn + should_stop`(Fix/Chat 两种 policy)。
- `ChatRunner`:注入 `MockLLMClient` + **假输入流**(预设用户行)+ **Spy presenter**(断言显示序列)。覆盖:read→edit→run_tests→Finish;HITL `y`/`n`;`/exit` `/clear` `/tests`;`--accept` 绿即停;预算耗尽。
- `split_prose_and_action`:prose + action / 纯发言(无 ACTION) / ParseError 回灌。
- Presenter:捕获输出快照断言。
- 真实 GLM 仅 gated `@pytest.mark.live`。

## 9. 改动文件清单

- 改:`src/harness/agent.py`(step-wise + Termination policy)、`src/harness/context/manager.py`(`build_chat`)、`src/harness/cli.py`(注册 `chat`/`task` 子命令;`fix` 保留为 `task --accept` 的别名或独立子命令)。
- 新:`src/harness/cli/chat.py`(ChatRunner)、`src/harness/cli/presenter.py`、`src/harness/agent_policy.py`(FixPolicy/ChatPolicy,或并入 agent.py)。
- 测试:`tests/unit/test_agent_step.py`、`tests/unit/test_presenter.py`、`tests/integration/test_chat_runner.py`、`tests/unit/test_split_prose.py`。

## 10. 与作业的映射

- §A.1 六维度:决策/工具/记忆/治理/反馈/配置 —— 全复用,交互外壳不改维度。
- §A.2"读写代码、执行命令、运行测试,据测试结果自我修正" —— 对话式自由修改 + run_tests 自纠 = 直接对应。
- §A.4-C:step/presenter/policy 全 mock 可单测,内核机制确定性不退化。
- 深做维度(反馈闭环)不变;chat 模式让它在 REPL 里可见(`show_feedback`)。
