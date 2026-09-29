"""OpenAI-compatible provider (spec section 29). Requires the `openai` extra.

Works with any OpenAI-compatible endpoint (OpenAI, Azure, local gateways) by
setting the base URL.
"""
from __future__ import annotations

from typing import Optional

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str], base_url: Optional[str],
                 default_model: str):
        try:
            import openai  # type: ignore
        except ImportError as e:  # pragma: no cover - env dependent
            raise RuntimeError(
                "openai package not installed. `pip install autocoder[openai]`"
            ) from e
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.OpenAI(**kwargs)
        self._default_model = default_model

    def generate(self, prompt: str, *, system=None, model=None,
                 temperature=0.2, max_tokens=4096) -> str:
        resp = self._client.chat.completions.create(
            model=model or self._default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system",
                 "content": system or "You are a precise software engineering assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""
