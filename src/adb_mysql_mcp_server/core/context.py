"""Global MCP instance context.

AdbMCP registers itself via set_mcp_instance() during __init__.
Other modules can retrieve the singleton via global_mcp_instance().
"""

from __future__ import annotations

from typing import Any

_mcp_instance: Any = None


def set_mcp_instance(instance: Any) -> None:
    """Register the global MCP instance (called by AdbMCP.__init__)."""
    global _mcp_instance
    _mcp_instance = instance


def global_mcp_instance() -> Any:
    """Return the global MCP instance. Raises RuntimeError if not initialised."""
    if _mcp_instance is None:
        raise RuntimeError("MCP instance has not been initialised yet.")
    return _mcp_instance
