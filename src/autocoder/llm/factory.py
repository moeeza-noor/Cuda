"""Provider factory: pick a provider from configuration (spec sections 29, 31)."""
from __future__ import annotations

from ..config import Config
from .base import LLMProvider
from .mock_provider import MockProvider


def build_provider(config: Config) -> LLMProvider:
    provider = config.provider.lower()
    if provider == "mock":
        return MockProvider()
    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            config.anthropic_api_key, config.anthropic_base_url, config.strong_model
        )
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(
            config.openai_api_key, config.openai_base_url, config.strong_model
        )
    if provider == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider(config.ollama_base_url, config.strong_model)
    raise ValueError(f"unknown provider: {config.provider}")
