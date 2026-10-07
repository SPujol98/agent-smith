"""Registry for managing and exposing agent tools."""
from __future__ import annotations

import inspect
from agent_smith.tools.base import BaseTool
from typing import Any


class ToolRegistry:
    """Registry to store, manage, and retrieve agent tools."""
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register an agent tool by its name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def get_namespace(self) -> dict[str, Any]:
        """Expose registered tools as callable functions
        in an execution namespace."""
        return {name: tool.safe_execute for name, tool in self._tools.items()}

    def get_manual(self) -> str:
        """Generate a text manual describing all registered tools."""
        lines: list[str] = ["Available Tools:"]
        for tool in self._tools.values():
            sig = inspect.signature(tool.execute)
            params = [name for name in sig.parameters.keys() if name != "self"]
            params_str = ", ".join(params)
            lines.append(f"- {tool.name}({params_str}): {tool.description}")
        return "\n".join(lines)
