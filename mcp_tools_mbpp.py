"""MCP server providing tools for MBPP task evaluation."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from agent_smith.sandbox.runner import SandboxRunner

# MCP Server instance
mcp = MCPServer("mbpp-tools")


@mcp.tool()
def run_tests(
    code: str,
    test_list: list[str],
    test_imports: list[str] | None = None,
) -> str:
    """Run test assertions against code; JSON with success and output."""
    imports_str = "\n".join(test_imports) if test_imports else ""
    tests_str = "\n".join(test_list)
    script = "\n\n".join([imports_str, code, tests_str])
    result = SandboxRunner().run(script)
    output = result.stdout + result.stderr + (result.error or "")
    return json.dumps(
        {"success": result.success, "output": output or "All tests passed."})


if __name__ == "__main__":
    mcp.run(transport="stdio")
