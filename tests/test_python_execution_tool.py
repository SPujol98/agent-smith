import pytest
from agent_smith.sandbox.runner import SandboxRunner
from agent_smith.tools.base import ToolError
from agent_smith.tools.python_execution import PythonExecutionTool


def test_python_execution_tool_success() -> None:
    # Arrange
    runner = SandboxRunner(authorized_imports=["math"])
    tool = PythonExecutionTool(runner)

    # Act
    output = tool.safe_execute(code="import math\nprint(math.sqrt(16))")

    # Imprime la representación exacta con comillas y saltos de línea (\n)
    print(f"\n[DEBUG OUTPUT]: {repr(output)}")

    # Assert
    assert tool.name == "python_interpreter"
    assert "4.0" in output


def test_python_execution_tool_captures_error() -> None:
    # Arrange
    runner = SandboxRunner()
    tool = PythonExecutionTool(runner)

    # Act
    output = tool.safe_execute(code="print(1 / 0)")

    # Assert
    assert "ZeroDivisionError" in output


def test_python_execution_tool_invalid_args() -> None:
    # Arrange
    runner = SandboxRunner()
    tool = PythonExecutionTool(runner)

    # Act & Assert
    with pytest.raises(ToolError):
        tool.safe_execute(invalid_param="print('hello')")
