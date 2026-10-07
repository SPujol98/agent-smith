"""Base contract for agent tools."""

from abc import ABC, abstractmethod
from typing import Any


class ToolError(Exception):
    """Exception raised when a tool fails or receives invalid arguments."""
    pass


class BaseTool(ABC):
    """Abstract base class representing an executable tool for an agent."""

    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Execute the tool logic and return a string observation."""
        pass

    def safe_execute(self, **kwargs: Any) -> str:
        try:
            return self.execute(**kwargs)
        except TypeError as e:
            raise ToolError(f"Invalid arguments for tool '{self.name}': {e}")
        except Exception as e:
            raise ToolError(f"Execution failed for tool '{self.name}': {e}")
