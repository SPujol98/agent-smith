"""Tests for turning MCP tools into Python functions."""

from collections.abc import Iterator

import pytest
from mcp.server.mcpserver import MCPServer

from agent_smith.sandbox.mcp_client import MCPClient, MCPToolError
from agent_smith.sandbox.runner import SandboxRunner


def _unknown_server() -> MCPServer:
    """A server the sandbox knows nothing about, built for the tests."""
    server = MCPServer("unknown-test-server")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @server.tool()
    def greet(name: str, greeting: str = "Hello") -> str:
        """Greet someone."""
        return f"{greeting}, {name}!"

    @server.tool()
    def describe(word: str) -> dict[str, int]:
        """Return the length of a word as an object."""
        return {"length": len(word)}

    @server.tool()
    def fail(reason: str) -> str:
        """Always fail."""
        raise ValueError(reason)

    return server


@pytest.fixture
def client() -> Iterator[MCPClient]:
    with MCPClient(_unknown_server()) as connected:
        yield connected


def test_one_function_per_tool(client: MCPClient) -> None:
    # Act
    functions = client.tool_functions()

    # Assert
    assert sorted(functions) == ["add", "describe", "fail", "greet"]
    assert functions["add"].__name__ == "add"
    assert functions["add"].__doc__ == "Add two integers."


def test_positional_and_keyword_arguments(client: MCPClient) -> None:
    # Arrange
    functions = client.tool_functions()

    # Act & Assert
    assert functions["add"](2, 3) == 5
    assert functions["add"](a=2, b=3) == 5
    assert functions["greet"]("Ana") == "Hello, Ana!"
    assert functions["greet"]("Ana", greeting="Hi") == "Hi, Ana!"


def test_wrong_number_of_arguments_raises_type_error(
    client: MCPClient,
) -> None:
    # Arrange
    add = client.tool_functions()["add"]

    # Act & Assert
    with pytest.raises(TypeError):
        add(1, 2, 3)
    with pytest.raises(TypeError):
        add(1, a=2)


def test_structured_result_is_returned_as_python_value(
    client: MCPClient,
) -> None:
    # Act
    value = client.tool_functions()["describe"]("hello")

    # Assert
    assert value == {"length": 5}


def test_tool_error_raises_mcp_tool_error(client: MCPClient) -> None:
    # Arrange
    fail = client.tool_functions()["fail"]

    # Act & Assert
    with pytest.raises(MCPToolError):
        fail("nope")


def test_missing_argument_is_reported_by_the_server(
    client: MCPClient,
) -> None:
    # Arrange
    add = client.tool_functions()["add"]

    # Act & Assert
    with pytest.raises(MCPToolError, match="b"):
        add(1)


def test_sandboxed_code_calls_mcp_tools(client: MCPClient) -> None:
    """End to end: code in the sandbox -> proxy -> parent -> MCP server."""
    # Arrange
    runner = SandboxRunner(functions=client.tool_functions())
    code = """
total = add(2, 3)
try:
    fail("broken")
except Exception as e:
    print(type(e).__name__)
final_answer(greet("sandbox"))
"""

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is True, result.error
    assert result.result_env["total"] == 5
    assert result.stdout == "MCPToolError\n"
    assert result.final_answer_value == "Hello, sandbox!"
