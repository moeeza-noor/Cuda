"""Anthropic provider (spec section 29). Requires the `anthropic` extra."""
from __future__ import annotations

from typing import Optional

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: Optional[str], base_url: Optional[str],
                 default_model: str):
        try:
            import anthropic  # type: ignore
        except ImportError as e:  # pragma: no cover - env dependent
            raise RuntimeError(
                "anthropic package not installed. `pip install autocoder[anthropic]`"
            ) from e
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.Anthropic(**kwargs)
        self._default_model = default_model

    def generate(self, prompt: str, *, system=None, model=None,
                 temperature=0.2, max_tokens=4096) -> str:
        resp = self._client.messages.create(
            model=model or self._default_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "You are a precise software engineering assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "".join(parts)
