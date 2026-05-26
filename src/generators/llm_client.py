"""LLM API 客户端封装, 支持 Anthropic Claude 和 OpenAI 兼容 API (Kimi/DeepSeek 等).

同时支持 disabled 模式: 当没有 API Key 时, 创建不可用实例,
配合 is_available() 方法让上层代码优雅降级.
"""

import os
from typing import AsyncIterator

# Anthropic SDK (Claude)
try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore

# OpenAI SDK (Kimi / DeepSeek / 其他兼容 OpenAI 的 API)
try:
    import openai
except ImportError:
    openai = None  # type: ignore


class ClaudeClient:
    """封装 LLM API 调用, 支持 Claude(Anthropic) 和 OpenAI 兼容格式(Kimi).

    通过环境变量自动判断使用哪个后端:
    - 如果设置了 ANTHROPIC_API_KEY, 使用 Claude API
    - 如果设置了 OPENAI_API_KEY, 使用 OpenAI 兼容 API
    - 如果同时设置, 优先使用 ANTHROPIC_API_KEY
    - 如果都没设置, 进入 disabled 模式 (is_available() 返回 False)
    """

    DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6-20251001"
    DEFAULT_OPENAI_MODEL = "moonshot-v1-32k"  # Kimi 默认模型

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """初始化 LLM 客户端.

        Args:
            api_key: API Key, 不传则自动从环境变量获取
            model: 模型名称, 不传则使用默认值
            base_url: API 基础 URL, 用于 OpenAI 兼容 API (如 Kimi)
        """
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")

        # 没有 API Key -> disabled 模式
        if not self._api_key:
            self.backend = "disabled"
            self.model = ""
            self.client = None
            self.async_client = None
            return

        # 判断后端类型
        self.backend = self._detect_backend(api_key)

        if self.backend == "anthropic":
            if anthropic is None:
                raise ImportError("anthropic package is required. Run: pip install anthropic")
            self.model = model or self.DEFAULT_CLAUDE_MODEL
            self.client = anthropic.Anthropic(api_key=self._api_key)
            self.async_client = anthropic.AsyncAnthropic(api_key=self._api_key)
        else:
            if openai is None:
                raise ImportError("openai package is required. Run: pip install openai")
            self.model = model or os.getenv("OPENAI_MODEL", self.DEFAULT_OPENAI_MODEL)
            self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
            self.client = openai.OpenAI(api_key=self._api_key, base_url=self.base_url)
            self.async_client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self.base_url)

    def _detect_backend(self, api_key: str | None) -> str:
        """检测使用哪个后端.

        优先级:
        1. 传入的 api_key 格式 (sk-ant-* = Anthropic)
        2. 环境变量 ANTHROPIC_API_KEY
        3. 环境变量 OPENAI_API_KEY
        4. 默认 openai
        """
        if api_key and api_key.startswith("sk-ant-"):
            return "anthropic"
        if api_key and api_key.startswith("sk-") and not api_key.startswith("sk-ant-"):
            return "openai"
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        return "openai"

    def is_available(self) -> bool:
        """返回 LLM 客户端是否可用."""
        return self.backend != "disabled"

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """同步调用 LLM API.

        Raises:
            RuntimeError: 如果客户端处于 disabled 模式
        """
        if self.backend == "disabled":
            raise RuntimeError("LLM client is disabled (no API key configured)")

        if self.backend == "anthropic":
            return self._chat_anthropic(messages, max_tokens, temperature, system)
        else:
            return self._chat_openai(messages, max_tokens, temperature, system)

    def _chat_anthropic(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        system: str | None,
    ) -> str:
        """调用 Anthropic Claude API."""
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

    def _chat_openai(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        system: str | None,
    ) -> str:
        """调用 OpenAI 兼容 API (Kimi/DeepSeek)."""
        openai_messages: list[dict] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    async def chat_async(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """异步调用 LLM API."""
        if self.backend == "disabled":
            raise RuntimeError("LLM client is disabled (no API key configured)")

        if self.backend == "anthropic":
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
        else:
            openai_messages: list[dict] = []
            if system:
                openai_messages.append({"role": "system", "content": system})
            openai_messages.extend(messages)

            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> AsyncIterator[str]:
        """流式调用 LLM API."""
        if self.backend == "disabled":
            raise RuntimeError("LLM client is disabled (no API key configured)")

        if self.backend == "anthropic":
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
        else:
            openai_messages: list[dict] = []
            if system:
                openai_messages.append({"role": "system", "content": system})
            openai_messages.extend(messages)

            stream = await self.async_client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
