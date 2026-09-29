"""LLM provider abstraction (spec section 29).

Providers are model-agnostic. The agent never hard-codes a single vendor; the
concrete provider is chosen at runtime from configuration.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional


class LLMProvider(ABC):
    """Common interface every provider implements."""

    name: str = "base"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Return a plain-text completion."""

    def generate_structured(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        schema_hint: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Return a parsed JSON object (spec section 30).

        Default implementation asks for JSON and robustly extracts it. Providers
        with native structured-output support may override.
        """
        instructions = (
            "Respond with a single valid JSON object and nothing else. "
            "Do not wrap it in prose or markdown fences."
        )
        if schema_hint:
            instructions += f"\nExpected shape:\n{schema_hint}"
        full = f"{prompt}\n\n{instructions}"
        raw = self.generate(
            full,
            system=system,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return extract_json(raw)

    def stream(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Default streaming: yield the whole completion once."""
        yield self.generate(
            prompt,
            system=system,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )


def extract_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from model output (spec section 30).

    Handles fenced blocks and leading/trailing prose. Falls back to a balanced
    brace scan.
    """
    if not text:
        raise ValueError("empty model output")
    text = text.strip()

    # Strip common markdown fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text = candidate

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Balanced-brace scan for the first complete JSON object.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    raise ValueError(f"could not parse JSON from model output: {text[:200]!r}")
