"""Tests for the synchronous MCP client facade."""
import sys
from pathlib import Path

import pytest
from agent_smith.sandbox.mcp_client import MCPClient, MCPConnectionError
from mcp.server.mcpserver import MCPServer

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _unknown_server() -> MCPServer:
    """A server the sandbox knows nothing about, built for the tests."""
    server = MCPServer("unknown-test-server")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @server.tool()
    def shout(text: str) -> str:
        """Return the text in upper case."""
        return text.upper()

    return server


def test_lists_tools_of_connected_server() -> None:
    # Act
    with MCPClient(_unknown_server()) as client:
        names = sorted(tool.name for tool in client.list_tools())

    # Assert
    assert names == ["add", "shout"]


def test_calls_tool_and_returns_result() -> None:
    # Act
    with MCPClient(_unknown_server()) as client:
        result = client.call_tool("add", {"a": 2, "b": 3})

    # Assert
    assert result.is_error is False
    assert result.structured_content == {"result": 5}


def test_stdio_transport_launches_the_server() -> None:
    # Arrange
    command = f"{sys.executable} {PROJECT_ROOT / 'mcp_tools_mbpp.py'}"

    # Act
    with MCPClient.from_stdio(command) as client:
        names = [tool.name for tool in client.list_tools()]

    # Assert
    assert "run_tests" in names


def test_connection_failure_raises_clear_error() -> None:
    # Act & Assert
    with pytest.raises(MCPConnectionError):
        with MCPClient.from_stdio("command-that-does-not-exist-xyz"):
            pass


def test_requests_after_close_are_rejected() -> None:
    # Arrange
    with MCPClient(_unknown_server()) as client:
        pass

    # Act & Assert
    with pytest.raises(MCPConnectionError):
        client.list_tools()
