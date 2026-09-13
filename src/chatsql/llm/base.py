"""LLM 抽象接口：所有模型客户端都实现这个协议。"""
from __future__ import annotations

from typing import Protocol

Message = dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


class LLMClient(Protocol):
    def chat(self, messages: list[Message]) -> str:
        """给定对话消息，返回模型的文本回复。"""
        ...
