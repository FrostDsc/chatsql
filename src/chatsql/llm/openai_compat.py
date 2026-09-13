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
    """离线 mock：从用户消息里提取 ```sql 代码块原样返回，否则返回固定 SQL。

    供无 API key 时开发和跑测试用（CHATSQL_MOCK=1）。
    """

    def __init__(self, canned_sql: str = "SELECT 1"):
        self._canned_sql = canned_sql
        self.calls: list[list[Message]] = []

    def chat(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        return f"```sql\n{self._canned_sql}\n```"
