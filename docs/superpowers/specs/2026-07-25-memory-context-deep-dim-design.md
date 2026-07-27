# Design Delta — Memory/Context Deep-Dim (Compaction + Retrieval + @mention)

> 第三个深做维度(作业 §A.3"记忆:按需提供给 LLM 而非全量载入" + §A.4-D"记忆/上下文为重点须自实现存储与检索")。让 agent 能**聊得很长不爆窗、记住项目、按需取文件/符号**,全自实现(不接框架 memory)。设计日期 2026-07-25。

## 1. Conversation Compaction(长对话不爆窗)—— 核心

- `Compactor`(`memory/compactor.py`):当对话 token 估算超 `context.compact_threshold`(默认 ~6000 chars 启发式),把**最早的 N 轮**(保留最近 K 轮原文)压成一条 `system` 摘要消息(`[compacted] <摘要>`),丢掉原文。
- 摘要怎么来?**自实现、确定性**:不调 LLM(那会引入不确定性 + 成本),而是**结构化摘要每轮**——对每个被压轮,取 `action 类型 + 路径 + 结果摘要(ok/fail)`(从 task_events/turns),拼成事实清单(如 `turn3: EditFile src/foo.py ok; turn4: RunTests tests/t.py RED(LOGIC)`)。这是纯函数、mock 可单测、零 LLM。
  - (LLM 摘要可作为未来 `--llm-compact` 选项;默认结构化摘要,保证 §A.4-C 确定性。)
- ContextManager.build_chat 在组装前先 `Compactor.maybe_compact(history)`。
- 单测:喂超阈值历史 → 断言被压成 1 条 system 摘要 + 保留最近 K 原文 + 摘要内容含每轮事实。

## 2. 项目记忆增强

- `MemoryStore` 已有 notes(HARNESS.md)+ JSONL log。增强:
  - 启动时自动载入 `<repo>/AGENTS.md`(若存在,标准项目记忆约定),与 HARNESS.md notes 合并进系统提示。
  - `MemoryStore.append_decision(text)`:agent 可主动记"决策/约定"到 notes(新动作 `remember`?或复用 finish 的 reason)。YAGNI——先只自动载入 AGENTS.md,不新增动作。
- 单测:AGENTS.md 存在时被载入系统提示。

## 3. @mention 拉文件

- 解析用户消息里的 `@<path>`(相对仓库根),在 build_chat 时把对应文件内容作为 `user` 消息注入(`<@src/foo.py>\n<内容>`),让 agent 不用 read_file 就能看到指定文件。bounded(总大小上限,超限只注入前若干 + 提示)。
- 单测:消息含 `@src/foo.py` → 上下文含该文件内容。

## 4. 自实现检索(符号/关键词)—— §A.4-D 要求自实现

- `Retriever`(`memory/retriever.py`):轻量、无外部向量库。两条:
  - **符号检索**:用 stdlib `ast` 扫描 `write_roots` 下 `.py`,建 `{符号名: 文件:行}`(函数/类/顶层赋值),`Retriever.find_symbol(name)` 返回定位。agent 可经新动作 `grep_symbol`/或在系统提示里告知"用 read_file 精确定位"。YAGNI——**最小实现**:暴露一个内部函数 `Retriever.symbols(root)` + 一个测试,证明符号索引自实现、可单测;不强行做向量。
  - **关键词检索**:`Retriever.grep(pattern, root)` 简易正则扫文件(行级),返回命中(文件:行:片段)。
- 这满足"存储与检索自实现";不接任何框架 memory。
- 单测:fixture 仓 → `symbols()` 含 `add@src/foo.py`;`grep("assert", root)` 命中测试行。

## 5. 接线与文件

- 新:`memory/compactor.py`、`memory/retriever.py`。
- 改:`context/manager.py`(compaction + AGENTS.md 载入 + @mention 解析)、`memory/store.py`(AGENTS.md 载入)、`config.py`(`[context] compact_threshold/keep_recent/mention_max_chars`)、`harness.toml.example`。
- 测试:`tests/unit/test_compactor.py`、`test_retriever.py`、`test_context_memory.py`、`tests/integration/test_chat_long_session.py`(超阈值 → 压缩 → 继续工作)。

## 6. 与作业映射

- §A.3 记忆"按需提供给 LLM 而非全量载入":compaction(不全量载历史)+ @mention(按需拉文件)+ retriever(按需定位符号)三件套,全自实现。
- §A.4-D:记忆/上下文为重点须自实现存储与检索——compactor/retriever 全 stdlib 自写,不接框架。
- §A.4-C:compactor/retriever/@mention 均确定性 mock 可单测。
