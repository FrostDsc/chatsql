"""OpenAI 兼容客户端：适配 DeepSeek / Qwen / OpenAI / Ollama 等端点。"""
from __future__ import annotations

from openai import OpenAI

from chatsql.config import ModelConfig
from chatsql.llm.base import Message


class OpenAICompatClient:
    def __init__(self, config: ModelConfig):
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )

    def chat(self, messages: list[Message]) -> str:
        resp = self._client.chat.completions.create(
            model=self._config.name,
            messages=messages,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )
        return resp.choices[0].message.content or ""


class MockClient:
    """离线 mock：默认返回固定 SQL；传入 responses 列表则逐次消费（脚本化）。

    供无 API key 时开发和跑测试用（CHATSQL_MOCK=1）。
    """

    def __init__(self, canned_sql: str = "SELECT 1", responses: list[str] | None = None):
        self._canned_sql = canned_sql
        self._responses = list(responses) if responses else None
        self.calls: list[list[Message]] = []

    def chat(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        if self._responses is not None:
            if self._responses:
                return self._responses.pop(0)
            return "（mock 响应已耗尽）"
        return f"```sql\n{self._canned_sql}\n```"
