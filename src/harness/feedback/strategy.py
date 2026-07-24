from harness.feedback.types import FailureCategory

def strategy_hint(category, *, nodeid="", expected=None, actual=None,
                  budget_s=None, exc="") -> str:
    if category is None:
        return ""
    if category is FailureCategory.ENV:
        return (f"测试未运行：{exc or '环境错误'}。先查依赖/导入/路径，"
                f"在收集成功前不要改断言逻辑。")
    if category is FailureCategory.LOGIC:
        ea = f"期望 {expected}，实际 {actual}。" if expected or actual else ""
        return f"断言失败@{nodeid}：{ea}修实现逻辑。"
    if category is FailureCategory.TIMEOUT:
        return f"测试超时（{budget_s}s）。疑似死循环或慢路径，重审算法。"
    return "未分类失败，原始 traceback 见下。先诊断再改。"
