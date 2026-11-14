"""Tests for MCP resources and prompts exposed in the sandbox."""

from collections.abc import Iterator

import pytest
from mcp.server.mcpserver import MCPServer

from agent_smith.sandbox.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPToolError,
)
from agent_smith.sandbox.runner import SandboxRunner


def _server_with_resources() -> MCPServer:
    server = MCPServer("resources-test-server")

    @server.resource("docs://guide", description="How to use the tools.")
    def guide() -> str:
        return "Use add(a, b)."

    @server.resource("data://numbers/{n}", description="Doubles n.")
    def numbers(n: str) -> str:
        return n * 2

    @server.prompt(description="Review some code.")
    def review(code: str, focus: str = "bugs") -> str:
        return f"Review this code for {focus}:\n{code}"

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    return server


@pytest.fixture
def client() -> Iterator[MCPClient]:
    with MCPClient(_server_with_resources()) as connected:
        yield connected


def test_list_resources_includes_templates(client: MCPClient) -> None:
    # Act
    resources = client.list_resources()

    # Assert
    uris = [resource["uri"] for resource in resources]
    assert uris == ["docs://guide", "data://numbers/{n}"]
    assert resources[0]["description"] == "How to use the tools."


def test_read_resource_returns_text(client: MCPClient) -> None:
    # Act & Assert
    assert client.read_resource("docs://guide") == "Use add(a, b)."
    assert client.read_resource("data://numbers/21") == "2121"


def test_read_unknown_resource_raises_tool_error(client: MCPClient) -> None:
    # Act & Assert
    with pytest.raises(MCPToolError, match="Unknown resource"):
        client.read_resource("docs://missing")


def test_list_and_get_prompts(client: MCPClient) -> None:
    # Act
    prompts = client.list_prompts()
    rendered = client.get_prompt("review", code="x = 1")

    # Assert
    assert prompts == [
        {
            "name": "review",
            "description": "Review some code.",
            "arguments": ["code", "focus"],
        }
    ]
    assert rendered == "user: Review this code for bugs:\nx = 1"


def test_sandbox_functions_combine_tools_and_helpers(
    client: MCPClient,
) -> None:
    # Act
    functions = client.sandbox_functions()

    # Assert
    assert set(functions) == {
        "add",
        "list_resources",
        "read_resource",
        "list_prompts",
        "get_prompt",
    }


def test_tool_name_clashing_with_helper_is_rejected() -> None:
    # Arrange
    server = MCPServer("clashing-server")

    @server.tool()
    def read_resource(uri: str) -> str:
        """A tool that hides the sandbox helper."""
        return uri

    # Act & Assert
    with MCPClient(server) as client:
        with pytest.raises(MCPConnectionError, match="read_resource"):
            client.sandbox_functions()


def test_sandboxed_code_reads_resources(client: MCPClient) -> None:
    # Arrange
    runner = SandboxRunner(functions=client.sandbox_functions())
    code = """
uris = [r["uri"] for r in list_resources()]
final_answer(read_resource(uris[0]))
"""

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is True, result.error
    assert result.final_answer_value == "Use add(a, b)."
