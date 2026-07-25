import os

import pytest

from harness.llm.zhipu import ZhipuLLMClient
from harness.types import Message


@pytest.mark.live
def test_real_completion_returns_text():
    key = os.environ.get("ZHIPU_API_KEY")
    if not key:
        pytest.skip("ZHIPU_API_KEY not set")
    c = ZhipuLLMClient(model="glm-4.6", api_key=key)
    out = c.complete(
        [
            Message("system", "Reply with the single word PONG."),
            Message("user", "ping"),
        ]
    )
    assert isinstance(out, str) and out.strip()
