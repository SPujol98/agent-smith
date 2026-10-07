"""MCP server providing tools for MBPP task evaluation."""
from __future__ import annotations

import traceback
from mcp.server.mcpserver import MCPServer

# MCP Server instance
mcp = MCPServer("mbpp-tools")


@mcp.tool()
def run_tests(candidate_code: str, test_list: list[str],
              test_imports: list[str] | None = None) -> str:
    """Run validation test assertions against candidate Python code.

    Args:
        candidate_code: The Python function implementation to test.
        test_list: A list of assertion strings to validate the implementation.

    Returns:
        A success message if all tests pass, or error details if a test fails.
    """
    imports_str = "\n".join(test_imports) if test_imports else ""
    tests_str = "\n".join(test_list)
    script = f"{imports_str}\n\n{candidate_code}\n\n{tests_str}"
    execution_namespace: dict[str, object] = {}
    try:
        exec(script, execution_namespace)
        return "All tests passed successfully."
    except AssertionError:
        return f"AssertionError: Test failed.\n{traceback.format_exc()}"
    except Exception as e:
        return (f"Execution error ({type(e).__name__}): {e}\n"
                f"{traceback.format_exc()}")


if __name__ == "__main__":
    mcp.run(transport="stdio")
