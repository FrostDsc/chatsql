"""按配置创建 LLM 客户端。"""
from __future__ import annotations

from chatsql.config import Settings
from chatsql.llm.base import LLMClient
from chatsql.llm.openai_compat import MockClient, OpenAICompatClient


def create_llm(settings: Settings) -> LLMClient:
    if settings.use_mock:
        return MockClient()
    return OpenAICompatClient(settings.model)
