"""AdbMCP -- FastMCP extension with deferred registration and toolset grouping.

Core design:
  1. @mcp.tool(group='openapi') does NOT immediately register the tool with FastMCP.
     Instead, the function metadata is stored in a _pending_registrations list.
  2. Calling mcp.activate(enabled_groups=['openapi']) iterates the list and registers
     only the components belonging to the specified groups with FastMCP.
  3. This "deferred registration" mechanism enables toolset grouping -- different
     deployments can selectively activate different groups of tools.

Usage:
  mcp = AdbMCP("server-name")

  @mcp.tool(group="openapi")
  async def my_tool(x: str) -> str: ...

  @mcp.resource("custom://uri", group="sql")
  async def my_resource() -> str: ...

  mcp.activate(enabled_groups=["openapi", "sql"])
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import Prompt

from .context import set_mcp_instance


class _ComponentType(Enum):
    """Enumeration of MCP component types."""
    TOOL = "tool"
    PROMPT = "prompt"
    RESOURCE = "resource"


@dataclass
class _RegistrableItem:
    """Metadata for a deferred component stored in _pending_registrations."""
    func: Callable
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    group: str
    item_type: _ComponentType


class AdbMCP(FastMCP):
    """FastMCP subclass adding deferred registration and toolset grouping.

    Workflow:
      1. Definition phase: collect tools/resources via @mcp.tool() / @mcp.resource()
      2. Activation phase: call mcp.activate(enabled_groups=[...]) to register them
    """

    DEFAULT_GROUP = "openapi"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._pending_registrations: list[_RegistrableItem] = []
        self._is_activated = False
        super().__init__(*args, **kwargs)
        set_mcp_instance(self)

    # -- Decorator overrides ---------------------------------------------------

    def tool(self, *dargs: Any, group: str = DEFAULT_GROUP, **dkwargs: Any) -> Callable:
        """Tool decorator. Supports both @mcp.tool() and @mcp.tool(group='xxx')."""
        if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
            func = dargs[0]
            self._pending_registrations.append(
                _RegistrableItem(func=func, group=group, item_type=_ComponentType.TOOL, args=(), kwargs={})
            )
            return func

        def decorator(fn: Callable) -> Callable:
            self._pending_registrations.append(
                _RegistrableItem(func=fn, group=group, item_type=_ComponentType.TOOL, args=dargs, kwargs=dkwargs)
            )
            return fn

        return decorator

    def prompt(self, *dargs: Any, group: str = DEFAULT_GROUP, **dkwargs: Any) -> Callable:
        """Prompt decorator. Same usage as tool()."""
        if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
            func = dargs[0]
            self._pending_registrations.append(
                _RegistrableItem(func=func, group=group, item_type=_ComponentType.PROMPT, args=(), kwargs={})
            )
            return func

        def decorator(fn: Callable) -> Callable:
            self._pending_registrations.append(
                _RegistrableItem(func=fn, group=group, item_type=_ComponentType.PROMPT, args=dargs, kwargs=dkwargs)
            )
            return fn

        return decorator

    def resource(self, *dargs: Any, group: str = DEFAULT_GROUP, **dkwargs: Any) -> Callable:
        """Resource decorator. Requires a URI as the first positional argument.

        Usage:
            @mcp.resource("custom://uri", group="sql")
            async def my_resource() -> str: ...
        """
        def decorator(fn: Callable) -> Callable:
            self._pending_registrations.append(
                _RegistrableItem(func=fn, group=group, item_type=_ComponentType.RESOURCE, args=dargs, kwargs=dkwargs)
            )
            return fn

        return decorator

    # -- Activation ------------------------------------------------------------

    def activate(self, enabled_groups: list[str]) -> None:
        """Register components from the specified groups with FastMCP.

        Can only succeed once; subsequent calls are silently ignored.

        Args:
            enabled_groups: List of group names to activate.
        Raises:
            ValueError: If enabled_groups contains undefined group names.
        """
        if self._is_activated:
            return

        self._validate_groups(enabled_groups)
        print(f"\n--- Activating Component Groups: {enabled_groups} ---")

        activated: list[_RegistrableItem] = []
        for item in self._pending_registrations:
            if item.group not in enabled_groups:
                continue
            kw = item.kwargs.copy()

            if item.item_type == _ComponentType.TOOL:
                kw.setdefault("name", item.func.__name__)
                super().add_tool(item.func, *item.args, **kw)
            elif item.item_type == _ComponentType.PROMPT:
                kw.setdefault("name", item.func.__name__)
                super().add_prompt(Prompt(fn=item.func, **kw))
            elif item.item_type == _ComponentType.RESOURCE:
                # Invoke FastMCP.resource() to get the real decorator, then apply
                parent_decorator = FastMCP.resource(self, *item.args, **kw)
                parent_decorator(item.func)

            activated.append(item)
            print(f"  Activated {item.item_type.value} '{item.func.__name__}' from group '{item.group}'")

        self._is_activated = True
        print("--- Activation Complete ---\n")
        self._debug_output(enabled_groups, activated)

    # -- Internal helpers ------------------------------------------------------

    def _validate_groups(self, enabled_groups: list[str]) -> None:
        """Validate that all enabled_groups exist among registered components."""
        defined = {it.group for it in self._pending_registrations}
        invalid = set(enabled_groups) - defined
        if invalid:
            raise ValueError(f"Unknown group(s): {sorted(invalid)}. Available: {sorted(defined)}")

    def _debug_output(self, enabled_groups: list[str], activated: list[_RegistrableItem]) -> None:
        """Print detailed activation info when TOOLSET_DEBUG=1."""
        if os.getenv("TOOLSET_DEBUG", "").lower() not in ("1", "true", "yes", "on"):
            return
        all_groups = sorted({it.group for it in self._pending_registrations})
        print("--- COMPONENT DEBUG OUTPUT ---")
        print(f"All defined groups: {all_groups}")
        print(f"Enabled groups: {sorted(enabled_groups)}")
        by_type: dict[str, list[_RegistrableItem]] = {}
        for it in activated:
            by_type.setdefault(it.item_type.value.upper() + "S", []).append(it)
        for type_label, items in sorted(by_type.items()):
            print(f"Activated {type_label}:")
            grouped: dict[str, list[str]] = {}
            for it in items:
                grouped.setdefault(it.group, []).append(it.func.__name__)
            for grp in sorted(grouped):
                for name in sorted(grouped[grp]):
                    print(f"  [{grp}] {name}")
        print("----------------------------\n")
