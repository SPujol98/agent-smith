"""Data models representing sandbox execution outcomes."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable value object holding the outcome of a code execution."""

    success: bool
    stdout: str
    stderr: str
    result_env: dict[str, Any]
    error: str | None = None
