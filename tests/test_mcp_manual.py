"""Tests for the tool manual generated from the server's schemas."""

import sys
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer

from agent_smith.sandbox.mcp_client import MCPClient
from agent_smith.sandbox.mcp_manual import _schema_type

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _unknown_server() -> MCPServer:
    server = MCPServer("manual-test-server")

    @server.tool()
    def search(
        pattern: str,
        paths: list[str],
        limit: int = 10,
        exact: bool | None = None,
    ) -> list[str]:
        """Search for a pattern.

        This second paragraph must not appear in the manual.
        """
        return []

    @server.tool()
    def counts(word: str) -> dict[str, int]:
        """Count letters."""
        return {}

    @server.tool()
    def undocumented(x: int) -> str:
        return str(x)

    @server.resource("docs://guide", description="How to use the tools.")
    def guide() -> str:
        return "..."

    @server.prompt(description="Review some code.")
    def review(code: str, focus: str = "bugs") -> str:
        return code

    return server


def test_manual_lists_tool_signatures_from_schemas() -> None:
    # Act
    with MCPClient(_unknown_server()) as client:
        manual = client.manual()

    # Assert
    assert (
        "- search(pattern: str, paths: list[str], limit: int = 10, "
        "exact: bool | None = None) -> list[str]: Search for a pattern."
    ) in manual
    assert "- counts(word: str) -> dict[str, int]: Count letters." in manual
    assert "- undocumented(x: int) -> str\n" in manual
    assert "second paragraph" not in manual


def test_manual_lists_resources_and_prompts() -> None:
    # Act
    with MCPClient(_unknown_server()) as client:
        manual = client.manual()

    # Assert
    assert "- docs://guide: How to use the tools." in manual
    assert "- review(code, focus): Review some code." in manual


def test_manual_omits_empty_sections() -> None:
    # Arrange
    server = MCPServer("tools-only")

    @server.tool()
    def ping() -> str:
        """Answer pong."""
        return "pong"

    # Act
    with MCPClient(server) as client:
        manual = client.manual()

    # Assert
    assert manual == (
        "Tools (call them as Python functions):\n- ping() -> str: Answer pong."
    )


def test_manual_of_mbpp_server() -> None:
    # Arrange
    command = f"{sys.executable} {PROJECT_ROOT / 'mcp_tools_mbpp.py'}"

    # Act
    with MCPClient.from_stdio(command) as client:
        manual = client.manual()

    # Assert
    assert manual.startswith(
        "Tools (call them as Python functions):\n"
        "- run_tests(candidate_code: str, test_list: list[str], "
        "test_imports: list[str] | None = None) -> str"
    )


@pytest.mark.parametrize(
    ("schema", "expected"),
    [
        ({"type": "string"}, "str"),
        ({"type": "array", "items": {"type": "integer"}}, "list[int]"),
        ({"anyOf": [{"type": "number"}, {"type": "null"}]}, "float | None"),
        ({"type": ["string", "null"]}, "str | None"),
        (
            {"type": "object", "additionalProperties": {"type": "boolean"}},
            "dict[str, bool]",
        ),
        ({"type": "object"}, "dict"),
        ({}, "Any"),
    ],
)
def test_schema_type_translates_json_schema(
    schema: dict[str, Any], expected: str
) -> None:
    """Pure unit test: no server needed."""
    assert _schema_type(schema) == expected
