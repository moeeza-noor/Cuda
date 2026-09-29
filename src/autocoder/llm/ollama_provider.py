"""Ollama (local) provider (spec section 29). Uses stdlib HTTP only."""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, default_model: str):
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    def generate(self, prompt: str, *, system=None, model=None,
                 temperature=0.2, max_tokens=4096) -> str:
        payload = {
            "model": model or self._default_model,
            "prompt": prompt,
            "system": system or "You are a precise software engineering assistant.",
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("response", "")
