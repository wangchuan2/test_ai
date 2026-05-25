"""Claude API 客户端封装."""

import os
from typing import AsyncIterator

import anthropic
from anthropic import AsyncAnthropic


class ClaudeClient:
    """封装 Claude API 调用，支持同步和异步模式."""

    DEFAULT_MODEL = "claude-sonnet-4-6-20251001"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key is required. Set ANTHROPIC_API_KEY env var or pass api_key."
            )

        self.model = model or self.DEFAULT_MODEL
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.async_client = AsyncAnthropic(api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """同步调用 Claude API.

        Args:
            messages: 消息列表
            max_tokens: 最大 token 数
            temperature: 温度参数
            system: 系统提示词

        Returns:
            AI 回复文本
        """
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    async def chat_async(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """异步调用 Claude API."""
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = await self.async_client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用 Claude API.

        Args:
            messages: 消息列表
            max_tokens: 最大 token 数
            temperature: 温度参数
            system: 系统提示词

        Yields:
            文本片段
        """
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
            "stream": True,
        }
        if system:
            kwargs["system"] = system

        async with self.async_client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
