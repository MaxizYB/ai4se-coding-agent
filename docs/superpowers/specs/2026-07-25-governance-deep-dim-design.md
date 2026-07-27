# Design Delta — Governance Deep-Dim (Sandbox + Diff-Preview + TaskReport)

> 第二个深做维度(作业 §A.4-D 点名"治理/沙箱")。在反馈闭环之外,把治理做深:执行级硬沙箱 + 写前 diff 预览审批 + 结构化任务总结报告。全为代码机制、确定性、mock 可单测(§A.4-B/C)。设计日期 2026-07-25。
> 内核主循环/工具/反馈/凭据不动;新增 `Sandbox`、`DiffPreviewer`/`DiffGate`、`TaskReport`,并在 agent/chat 循环里接线。

## 1. Sandbox(代码边界为主 + 可选 Docker)—— 已批

新组件 `src/harness/guardrails/sandbox.py`。dispatcher 执行 `RunShell`/`RunTests` 前再过一道**硬边界**(Guardrail 管"问人",Sandbox 管"无论如何不许/限网络/限 FS"):

| 边界 | 机制 | 默认 |
|------|------|------|
| 命令 denylist | `sandbox.denied_commands` 正则 → `Deny`(不问不跑) | 破坏性 `rm -rf /`/`mkfs`/`dd of=`/fork bomb/`> /dev/sd*` |
| 网络 egress | `sandbox.network` ∈ `offline`/`allowlist`/`open`;命中网络工具集且不在 `network_allow` → `offline` 硬拒 / `allowlist` 问人 | `offline`(默认禁网) |
| FS 写范围 | `sandbox.write_roots`(默认 `["src"]`)越界写硬拒;`read_roots` 可选 | `src` |

- `Sandbox.check(action) -> Allow | Deny(reason) | AskHuman(reason) | Containerize`。
- dispatcher 顺序:`guardrail.check` → 若 RunShell/RunTests:`sandbox.check` → HITL(若 AskHuman)→ 执行 **或** 容器执行器。
- **可选 B**:`SandboxDockerExecutor`(`sandbox.containerize=true`)→ `docker run --rm --network=none -v <repo>:/work -w /work <image>`(禁网、系统只读、仅仓库可写)。执行器是接口,docker 调用可 mock(单测),真实容器=集成测。默认关。
- 配置见 `harness.toml [sandbox]`(`network`/`network_allow`/`denied_commands`/`write_roots`/`containerize`/`container_image`)。

## 2. DiffPreviewer + DiffGate(写前预览审批)

- `DiffPreviewer.preview(action, project_root) -> (path, diff_text)`:对 `WriteFile`/`EditFile` 计算应用后的内容(读当前文件,对 edit 做 old→new 替换,对 write 取 content),用 `difflib.unified_diff` 生成 diff。纯函数(仅读当前文件)。
- **DiffGate**(在 agent/chat 循环里,dispatcher 之外——保持 dispatcher 纯):对 write/edit,依 `diff.preview`(`always`/`ask`/`never`,默认 `ask` 交互、非交互 fail-closed 拒):`ask` → `presenter.show_diff(path, diff)` + `approver.ask(...)` → 放行才 `dispatcher.execute`;`always` → 展示后直接执行;`never` → 静默执行。
- ChatRunner 用 `ConsoleApprover`;AgentRunner(fix)用 `FailClosedApprover`(非交互 → 不预览直接执行或拒,依配置)。
- 单测:`DiffPreviewer.preview` 快照断言;`DiffGate` 用 StubApprover 验放行/拒绝;非交互 fail-closed。

## 3. TaskReport(结构化任务总结)

- agent/chat 循环维护结构化 **task_events** 列表(`{kind: "file_changed"|"test"|"shell", detail, ok?}`),随执行追加(确定性)。
- `TaskReport.build(task_events, outcome, agent_summary) -> TaskReport{outcome, files_changed:list[str], commands_run:list[str], tests:list[{selector, green}], summary}`。
- 终止时(Finish/SUCCESS/REPLIED/BUDGET)`presenter.show_report(report)`;`harness task` 末尾打印。
- `summary` = agent 的 Finish reason / 末段 prose(非 AI 二次生成,YAGNI)。
- 单测:喂 canned task_events → 断言聚合字段。

## 4. 接线与文件

- 新:`guardrails/sandbox.py`、`guardrails/sandbox_docker.py`(可选 B)、`governance/diff_preview.py`(DiffPreviewer)、`governance/task_report.py`(TaskReport)。
- 改:`tools/dispatcher.py`(接 Sandbox + 记 task_events)、`interactive/chat.py` + `agent.py`(DiffGate + TaskReport 展示 + task_events)、`config.py`(`[sandbox]`/`[diff]`)、`harness.toml.example`、`interactive/presenter.py`(`show_diff`/`show_report`)。
- 测试:`tests/unit/test_sandbox.py`、`test_diff_preview.py`、`test_task_report.py`、`tests/integration/test_chat_governance.py`、可选 `test_sandbox_docker.py`(mock docker)。

## 5. 与作业映射

- §A.4-D 治理/沙箱:从 guardrail+HITL 升级到**执行级硬沙箱**(+可选真容器隔离)。深做。
- §A.6 演示③ 可对齐到本维度(Sandbox 拦截危险/越网命令 = 治理确定性行为),与反馈维度并列。
- §A.4-B/C:全代码、确定性、mock 单测;Docker 真跑为集成测。
