# REFLECTION.md

> ⚠️ **本文件由学生本人撰写（§六：反思报告禁止 AI 代写，可用 AI 辅助润色但需标注）。**
> 以下是 §五.8 建议回答的问题清单与字数要求，作为写作骨架。**内容请自行填写。**
> 字数要求：1500–2500 字。

---

## 建议回答的问题（§五.8）

1. **哪些 Superpowers 技能发挥了最大作用？哪些"形式大于实质"？**
2. **TDD 强制在 AI 协作下是阻碍还是放大器？**
3. **subagent-driven 工作流让智能体能自主运行多久而不偏离主题？**
4. **什么样的 task 颗粒度最优？**
5. **SPEC / PLAN 质量如何影响实现质量？**（举一个"规约不清导致 subagent 偏离"的具体案例——提示：本项目中可参考冷启动的 F1 nodeid 命名空间、或集成阶段 C2 工具观测不回灌、或 PR5 demo 的 fixture/conftest 缺失。）
6. **你最有效的 prompt / context 策略是什么？为什么有效？**
7. **凭据与分发这两条工程要求，迫使你想清楚了哪些原本会忽略的问题？**
8. **如果重做你会改变什么？**
9. **对 Superpowers 这套方法论的批判——它假设了什么？这些假设在你的项目里成立吗？**

---

## 写作可引用的客观素材（来自 AGENT_LOG.md / SPEC_PROCESS.md，非代写）

- 冷启动验证 11 条 findings（`SPEC_PROCESS.md §5`），最深为 F1 nodeid 命名空间（task 边界不可见）。
- 集成阶段 2 个 Critical（C1 真实 pytest 无 `type=` → UNKNOWN；C2 工具观测不回灌）——均被 mock 假绿掩盖。
- PR5 评审 2 个 Critical（CI 缺 fastapi；§五.9 demo ERROR 被宽松断言掩盖）。
- 全程 5 PR / 23 task / 108 测试 / 0 警告 / ruff clean。

<!-- 学生反思正文写在此分隔之下。 -->
