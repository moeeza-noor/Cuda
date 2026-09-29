"""autocoder — an autonomous software-engineering agent.

Public API:
    from autocoder import Orchestrator, Config
    report = Orchestrator(Config.load()).run("build a task API")
"""
from .config import Config
from .core.orchestrator import Orchestrator

__version__ = "0.1.0"
__all__ = ["Config", "Orchestrator", "__version__"]
