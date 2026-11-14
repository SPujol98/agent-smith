"""Tests for SandboxRunner connected to an MCP server."""

import sys
from pathlib import Path

import pytest

from agent_smith.sandbox.mcp_client import MCPConnectionError
from agent_smith.sandbox.runner import SandboxRunner

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MBPP_SERVER = f"{sys.executable} {PROJECT_ROOT / 'mcp_tools_mbpp.py'}"


def _write_server(tmp_path: Path, body: str) -> str:
    """Write a small MCP server script and return the command to run it."""
    script = tmp_path / "server.py"
    script.write_text(
        "import os\n"
        "from mcp.server.mcpserver import MCPServer\n"
        "server = MCPServer('test-server')\n"
        f"{body}\n"
        "server.run(transport='stdio')\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script}"


def test_runner_without_mcp_documents_final_answer() -> None:
    # Act
    with SandboxRunner() as runner:
        result = runner.run("final_answer('done')")

    # Assert
    assert "final_answer(answer: str)" in runner.manual
    assert result.final_answer_value == "done"


def test_runner_exposes_mcp_tools_and_manual() -> None:
    # Arrange
    code = """
report = run_tests("def f():\\n    return 1", ["assert f() == 1"])
final_answer(report)
"""

    # Act
    with SandboxRunner(mcp_stdio=MBPP_SERVER) as runner:
        manual = runner.manual
        result = runner.run(code)

    # Assert
    assert "final_answer(answer: str)" in manual
    assert "- run_tests(candidate_code: str" in manual
    assert result.success is True, result.error
    assert result.final_answer_value == "All tests passed successfully."


def test_mcp_env_reaches_the_server(tmp_path: Path) -> None:
    # Arrange
    command = _write_server(
        tmp_path,
        "@server.tool()\n"
        "def container() -> str:\n"
        "    return os.environ.get('SWE_CONTAINER', 'missing')\n",
    )

    # Act
    with SandboxRunner(
        mcp_stdio=command, mcp_env={"SWE_CONTAINER": "box-42"}
    ) as runner:
        result = runner.run("final_answer(container())")

    # Assert
    assert result.final_answer_value == "box-42"


def test_server_tool_cannot_replace_final_answer(tmp_path: Path) -> None:
    # Arrange
    command = _write_server(
        tmp_path,
        "@server.tool()\n"
        "def final_answer(answer: str) -> str:\n"
        "    return answer\n",
    )

    # Act & Assert
    with pytest.raises(MCPConnectionError, match="final_answer"):
        with SandboxRunner(mcp_stdio=command):
            pass


def test_connection_failure_is_reported() -> None:
    # Act & Assert
    with pytest.raises(MCPConnectionError):
        with SandboxRunner(mcp_stdio="command-that-does-not-exist-xyz"):
            pass


def test_stdio_and_url_are_mutually_exclusive() -> None:
    # Act & Assert
    with pytest.raises(ValueError):
        SandboxRunner(mcp_stdio="python server.py", mcp_url="http://x")
