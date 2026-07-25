from harness.types import Message

_BASE = "https://open.bigmodel.cn/api/paas/v4"


class ZhipuLLMClient:
    def __init__(self, model: str, api_key: str, base_url: str = _BASE):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    def complete(self, messages: list[Message]) -> str:
        import httpx

        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        r = httpx.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
