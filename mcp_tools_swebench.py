from mcp.server.mcpserver import MCPServer
from pathlib import Path

# MCP Server instance
mcp = MCPServer("swebench-tools")


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read file content with line numbers in cat -n format."""
    try:
        with open(Path(filepath), 'r', encoding='utf-8',
                  errors='replace') as f:
            lines = f.read().splitlines()
            slice_lines = lines[max(1, start_line) - 1: end_line]
            formatted = [f"{num}: {line}" for num, line in enumerate(
                slice_lines, start=max(1, start_line))]
            return "\n".join(formatted)
    except FileNotFoundError:
        return f"Error: File '{filepath}' not found."
    except Exception as e:
        return f"Error: File '{filepath}' not found: {e}."


if __name__ == "__main__":
    mcp.run(transport="stdio")
