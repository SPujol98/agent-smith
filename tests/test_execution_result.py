"""Unit tests for the ExecutionResult data model."""
import pytest

from agent_smith.sandbox.result import ExecutionResult


def test_execution_result_instantiation() -> None:
    # Arrange & Act
    result = ExecutionResult(
        success=True,
        stdout="Hello world\n",
        stderr="",
        result_env={"x": 42},
    )

    # Assert
    assert result.success is True
    assert result.stdout == "Hello world\n"
    assert result.stderr == ""
    assert result.result_env == {"x": 42}
    assert result.error is None


def test_execution_result_is_immutable() -> None:
    # Arrange
    result = ExecutionResult(
        success=True,
        stdout="",
        stderr="",
        result_env={},
    )

    # Act & Assert
    with pytest.raises(AttributeError):
        # ttype: ignore para comprobar la inmutabilidad en runtime
        result.success = False  # type: ignore[misc]
