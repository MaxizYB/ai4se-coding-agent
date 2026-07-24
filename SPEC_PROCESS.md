# SPEC_PROCESS.md

> 过程文档：记录与 Superpowers 协作生成 SPEC 与 PLAN 的过程（§4.4），以及用"陌生"智能体冷启动试运行 SPEC+PLAN 的客观证据（§4.5）。
> 主开发智能体：OpenCode（glm-5.2，zhipuai-coding-plan）。冷启动验证智能体：OpenCode `general` 子 agent（全新会话、无对话历史、仅给 SPEC+PLAN）。

---

## 一、brainstorming 关键节点（§4.4）

`brainstorming` 技能以"一次一个问题"驱动设计。它追问的最有价值的几个节点，以及我据此做的修正：

1. **"哪个维度做深？"** —— 这是它问的第一个、也是最高杠杆的问题。我推荐**反馈闭环**（最契合 §A.4-C 的"换 mock 仍可确定性单测"，且是 §A.6 机制演示②的中心展品），用户采纳。这个问题把"六个维度浅尝辄止"的风险提前消解。
2. **"自修正做到多深？"** —— 追问把"反馈闭环"从一句口号逼成具体的三段（分类 → 策略映射 → 卡住检测），直接决定了 PLAN 里 T3–T7 的密度。
3. **架构分叉："主循环怎么从 LLM 拿到结构化动作？"** —— 这是技能流程里"提 2–3 方案"那一步逼出来的。我提了原生 tool-calling / 结构化文本协议 / 混合三案，推荐**结构化文本协议（B）**。这一步把 §A.4-A"只许用底层 chat-completion、其余自己造"的红线提前对齐——如果没有这一问，很容易滑向 tool-calling，从而寄生供应商的 tool 协议。

---

## 二、≥3 轮关键迭代与我的处理决策

### 迭代 1：Context 被我低估，用户推翻了我的框架
- **我的初始提案**：把 `ContextManager` 归入"最低凑合实现"（因为反馈闭环是唯一深做维度）。
- **用户的反馈**："够，但其实 context 也很重要。"
- **我的处理**：承认这个框架错了——context 是反馈闭环的**投递载体**，hint 再准塞进噪声里也白搭。我提了三档（工程化投递层 / 升为并列第二深维度 / 维持最低），用户选**工程化投递层**。于是 `ContextManager` 多了四个可单测机制（选择策略 / 有界裁剪 / 反馈强调 / 当前快照），但深度仍归反馈闭环，不违反 §A.4-D。
- **教训**：技能的"非深做维度保持最低"框架，差点让我把 context 写水。用户的判断力在这里不可替代。

### 迭代 2：§五.9 WebUI 是个 scope 意外
- **发现**：写到最后一节核对交付清单时，发现 §五.9 无条件规定"线上部署 URL，必须提供应用可访问的 WebUI 接口"。Harness 本是 CLI 原生，这条是 MUST。
- **我的处理**：在设计的第 7 节显式标红，给三选项（加薄 WebUI / 用 Open Design / 论证豁免），用户选**加薄 WebUI + 部署**。它被严格界定为 `AgentRunner` 之上的纯展示层，不稀释内核深度。
- **教训**：brainstorming 技能本身不会在设计中段提醒你去逐条核对"最终交付清单"。我是在收尾时才扫到 §五.9——如果没扫到，后面会返工。

### 迭代 3：CI 表述不一致（§4.8 vs §五.6）
- **发现**：§4.8 写"CI（GitHub Actions）必须配置"；§五.6 写"`.gitlab-ci.yml`，必须包含名为 `unit-test` 的 job"。两处冲突。
- **我的处理**：以具有约束力的"最终交付清单"§五.6 为准 → 提供 `.gitlab-ci.yml`（含 `unit-test` job + 镜像构建），GH Actions 作可选。记入 SPEC §10-R1。

---

## 三、AI 提议 vs 我的取舍

| AI 提议 | 我的处理 | 原因 |
|--------|---------|------|
| 反馈闭环做深 | **采纳** | 最契合 §A.4-C，可确定性单测 |
| Python 实现 | **采纳** | subprocess+解析最顺、可 dogfood |
| 结构化文本协议（非 tool-calling） | **采纳** | 贴合 §A.4-A，provider 无关，mock 极简 |
| junit XML 作确定性主数据源（不扒文本） | **采纳** | 稳定、可喂 canned XML 断言 |
| `ContextManager` 归"最低" | **推翻**（用户主导） | context 是反馈投递载体，需工程化 |
| CLI-only，不做 WebUI | **推翻**（§五.9 强制） | 交付清单 MUST |
| Fernet 主密码加密文件 | **采纳** | 全平台、自实现、可单测 |

---

## 四、对 brainstorming 技能的反思

**做得好**：一次一问、多选优先、分节签字，有效控制了设计发散；"提 2–3 方案"那步把架构分叉（动作协议）显式化，避免滑向寄生框架；最后强制自审（占位符/一致性/范围/歧义）抓住了 US3 与治理语义的矛盾。

**做得不足**：
- 它的"非深做维度=最低"框架，诱导我把 context 写水（被用户纠偏）。
- 它不会在设计中段驱动你逐条核对"最终交付清单"——§五.9 的 WebUI 是我收尾手动扫出来的。
- 它假设"分节签字"等价于"全局一致"，但跨节的接口契约（如下文 F1 的 nodeid 命名空间）它不替你校验——这恰恰是冷启动验证暴露的最深问题。

---

## 五、冷启动验证（§4.5）—— 最关键的客观证据

### 5.1 设置
- **第二个智能体**：OpenCode `general` 子 agent，**全新会话、不导入任何先前对话或 memory**。
- **仅提供**：`SPEC.md` + `PLAN.md`（从磁盘自读），不补任何口头解释。
- **指派任务**：自主实现 PLAN 的 T0（脚手架）+ T3（反馈类型 + junit 解析）+ T4（失败分类）—— 恰是深做维度的核心两 task，约 1 小时。
- **指令**："遇到不确定之处即暂停询问（记录），而非凭猜测继续。"

### 5.2 结果
- **代码**：3 个 commit，15 文件 +207 行，**9/9 测试全绿**。
- **但**：返回 **11 条 findings**，证明"局部全绿 ≠ 全局正确"。

### 5.3 暴露的 SPEC/PLAN 缺陷（按严重度，前 5 条）

**F1 — CRITICAL：nodeid 命名空间 ≠ `--test` 选择器命名空间**
- 解析器输出 `nodeid = "classname.name"`（如 `t.Tests.test_add`），而 harness 其余部分用 pytest 选择器 `tests/test_foo.py::test_add`。两者永不字符串相等。
- 子 agent 的原话："a fresh implementer can produce a fully-green parser+classifier that *looks* correct in isolation, yet emits failure identifiers that are useless to the rest of the harness."
- **为何严重**：此缺陷在 task 边界不可见，只在集成（T17）才暴露，届时契约已锁死。

**F3 — HIGH：`is_green` 丢了 `exit_code==0`**
- SPEC §3.6 明确 `failed==0 && errors==0 && exit_code==0`；PLAN 的 `TestRunResult.is_green` 只查前两项。

**F2 — HIGH：TIMEOUT 从 stderr 兜底分支不可达**
- 正则 `[...]Error|[...]Exception` 不匹配 `TimeoutExpired`。实测 `parse_pytest_output(124,"","...TimeoutExpired...","")` 归类成 UNKNOWN 而非 TIMEOUT。

**F6 — MEDIUM：分类器精确串匹配，遇带模块前缀的真名即失效**
- 真实 pytest stderr 打印 `subprocess.TimeoutExpired`、`json.decoder.JSONDecodeError`，裸名集合匹配不到。

**F7 — MEDIUM：`CollectionError` 是个幽灵**
- `_ENV` 集合含 `CollectionError`，但 Python 无此内建异常；pytest 收集错误以其底层异常类型上报。

（另有 F4 Task0 期望 exit 码错、F5 stderr 链式异常取首/取末未定、F8 脚手架装全量依赖不 hermetic、F9 `TestFailure`/`TestRunResult` 触发 pytest 收集警告、F10 SPEC §3.8 列了 PLAN 没定义的 `stuck_signature`、F11 PLAN 加了 SPEC 没列的 `max_history`。）

### 5.4 子 agent 是否解读偏了我的原意？
**基本没有偏离**——它逐字照抄 PLAN 的代码，0 处代码 divergence。这恰恰是最锋利的发现：**问题不在"它会不会做"，而在"plan 优化的是局部绿、而非全局对"**。一个忠实遵循 TDD 的全新实现者会过每一道门，却仍交付一个"反馈标识无人能消费"的反馈闭环。

### 5.5 据此对 SPEC / PLAN 做的修订（before → after）

**修 F3（PLAN Task 3 `TestRunResult`）**
```diff
 @dataclass
 class TestRunResult:
+    __test__ = False
     ...
     failures: list[TestFailure] = field(default_factory=list)
+    exit_code: int = 0
     @property
     def is_green(self) -> bool:
-        return self.failed == 0 and self.errors == 0
+        return self.failed == 0 and self.errors == 0 and self.exit_code == 0
```

**修 F2 / F5（PLAN Task 3 stderr 兜底）**
```diff
-_EXC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*Error|[A-Za-z_][A-Za-z0-9_.]*Exception):")
+_EXC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Expired)):")
-m = _EXC_RE.search(stderr); exc = m.group(1) if m else "UnknownError"
+matches = _EXC_RE.findall(stderr); exc = matches[-1] if matches else "UnknownError"
```

**修 F6 / F7（PLAN Task 4 分类器）**
```diff
-_ENV = {"ModuleNotFoundError", "ImportError", "CollectionError", "SyntaxError"}
+_ENV = {"ModuleNotFoundError", "ImportError", "SyntaxError"}
-if failure.exc_type == "TimeoutExpired":
+exc = failure.exc_type.rsplit('.', 1)[-1]
+if exc == "TimeoutExpired":
```

**修 F1（PLAN Task 3 文档 + Task 7 设计说明）**：`_nodeid` 注释明确"junit 给的是 classname+name 而非 pytest 选择器"；correlation 由 Task 7 以**测试名后缀匹配**处理（红绿修复器通常只盯一个测试，名后缀匹配稳健）。`failing[]` 作为展示用，卡住检测的签名不受命名空间影响。

**修 F4 / F8 / F9（PLAN Task 0/3 脚手架）**：Task 0 期望改为"exit 5 或 0、无收集错误"；重依赖移入 `[full]` extra，核心 `dependencies=[]`（T1–T10 保持 stdlib-only、hermetic）；`TestFailure`/`TestRunResult` 加 `__test__ = False`。

**修 F10 / F11（SPEC §3.8）**：删去 PLAN 未定义的 `feedback.stuck_signature`；补入 PLAN 已用的 `context.max_history`。

> 子 agent 的实现留在分支 `coldstart/t3-t4` 作为客观证据（3 commit、9 绿）。因修订后 T3/T4 代码已更新，正式实现阶段将在 worktree 上按修订后的 PLAN 重新实现，该分支仅作验证留档。

### 5.6 这步验证的价值（反思）
- 冷启动前，SPEC+PLAN 在我和主 agent 之间有大量隐性共识，我严重高估了它们的清晰度。
- 最深的 F1（命名空间）是任何数量的"分节签字"都抓不到的——只有让一个**没有共享上下文**的实现者真的去接，才会暴露。
- 这印证了 §4.5 的论断：单人项目里，"换一个全新 agent 实现"是最接近同侪评审的内部机制。它把"看起来对"和"真的对"分开了。
