"""clawagentskill — Agent & skill discovery, security scanning, and adoption for OpenClaw."""

__version__ = "0.1.0"

from clawagentskill.config import load_config
from clawagentskill.state import StateManager

__all__ = ["__version__", "load_config", "StateManager"]
