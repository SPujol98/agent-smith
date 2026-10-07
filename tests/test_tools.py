"""Tests for agent tools and registry."""
import pytest
from agent_smith.tools.base import BaseTool, ToolError
from agent_smith.tools.registry import ToolRegistry


class DummyEchoTool(BaseTool):
    name: str = "echo"
    description: str = "Returns the received text."

    def execute(self, text: str) -> str:  # type: ignore[override]
        return text


def test_tool_instantiation_and_execution() -> None:
    # Arrange
    tool = DummyEchoTool()

    # Act
    output = tool.execute(text="hello agent")

    # Assert
    assert tool.name == "echo"
    assert "Returns the rec" in tool.description
    assert output == "hello agent"


class DummyCalculatorTool(BaseTool):
    name: str = "calculator"
    description: str = "Sum two integers."

    def execute(self, a: int, b: int) -> str:  # type: ignore[override]
        return str(a + b)


def test_tool_fails_gracefully_on_missing_or_invalid_arguments() -> None:
    # Arrange
    tool = DummyCalculatorTool()

    # Act & Assert
    # If missing arguments or mismatched type, must throw our Tool Exception
    with pytest.raises(ToolError):
        tool.safe_execute(a=5)  # Miss 'b'


def test_resgitry_saves_registered_tools() -> None:
    # Arrange
    tool = DummyEchoTool()
    registry = ToolRegistry()

    # Act
    registry.register(tool)

    # Assert
    retrieved_tool = registry.get("echo")
    assert retrieved_tool is not None
    assert retrieved_tool.name == "echo"


def test_registry_get_tools_name() -> None:
    # Arrange
    tool = DummyEchoTool()
    registry = ToolRegistry()
    registry.register(tool)

    # Act
    namespace = registry.get_namespace()

    # Assert
    assert isinstance(namespace, dict)
    assert "echo" in namespace
    assert callable(namespace["echo"])
    assert namespace["echo"](text="hello agent") == "hello agent"


def test_registry_generates_dynamic_manual() -> None:
    # Arrange
    registry = ToolRegistry()
    registry.register(DummyEchoTool())
    registry.register(DummyCalculatorTool())

    # Act
    manual = registry.get_manual()
    print(manual)

    # Assert
    assert isinstance(manual, str)
    assert "echo" in manual
    assert "Returns the received text." in manual
    assert "text" in manual
    assert "calculator" in manual
    assert "Sum two integers." in manual
    assert "a" in manual and "b" in manual
