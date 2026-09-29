"""Shared base for specialized agents (spec section 28)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..config import Config
from ..core.logging_utils import EventLog
from ..llm.base import LLMProvider


class BaseAgent:
    name = "agent"

    def __init__(self, llm: LLMProvider, config: Config, log: EventLog):
        self.llm = llm
        self.config = config
        self.log = log

    def _structured(self, prompt: str, *, kind: str, model: Optional[str] = None,
                    system: Optional[str] = None,
                    schema_hint: Optional[str] = None) -> Dict[str, Any]:
        """Ask the model for structured JSON, tagging the request kind.

        The `[[KIND:...]]` tag lets deterministic providers route reliably and
        is harmless to live providers.
        """
        tagged = f"[[KIND:{kind}]]\n{prompt}"
        return self.llm.generate_structured(
            tagged, system=system, model=model, schema_hint=schema_hint
        )
