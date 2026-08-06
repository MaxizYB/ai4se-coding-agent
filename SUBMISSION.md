# 提交信息

## 仓库链接

https://github.com/MaxizYB/ai4se-coding-agent

## Release 链接

https://github.com/MaxizYB/ai4se-coding-agent/releases/tag/v1.0.0

## CI 记录

https://github.com/MaxizYB/ai4se-coding-agent/actions

---

## 交付物清单（全部在仓库内）

| # | 交付物 | 位置 |
|---|--------|------|
| 1 | SPEC.md | 仓库根 |
| 2 | PLAN.md（含 Task Status Summary） | 仓库根 |
| 3 | SPEC_PROCESS.md | 仓库根 |
| 4 | 完整源代码 + mock-LLM 单元测试（240 tests） | `src/` `tests/` |
| 5 | AGENT_LOG.md | 仓库根 |
| 6 | REFLECTION.md（学生本人撰写） | 仓库根 |
| 7 | README.md（安装/运行/分发/目录/安全/限制） | 仓库根 |
| 8 | Dockerfile | 仓库根 |
| 9 | CI 配置（GitHub Actions `unit-test` job） | `.github/workflows/ci.yml` |
| 10 | §A.6 机制演示（①护栏 ②反馈改动作 ③分类差异） | `scripts/mechanism_demo.py` |
| 11 | 分发产物（wheel + sdist） | Release v1.0.0 附件 |

## CI 状态

最后一次 CI 执行：**pass**（unit-test ✓ + docker-image ✓ + build ✓）
