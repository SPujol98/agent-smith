import re
import subprocess
import os

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


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string."""
    try:
        path = Path(filepath)
        if not path.is_file():
            return f"Error: File '{filepath}' not found."
        content = path.read_text(encoding='utf-8')
        if old_str not in content:
            return (f"Error: String '{old_str}' not found in "
                    f"'{filepath}'.")
        new_content = content.replace(old_str, new_str, 1)
        path.write_text(new_content, encoding='utf-8')
        return f"Successfully updated '{filepath}'."
    except Exception as e:
        return f"Error editing file '{filepath}': {e}"


@mcp.tool()
def list_files(directory: str, pattern: str) -> str:
    """List files in a directory matching a given pattern."""
    try:
        path = Path(directory)
        if not path.is_dir():
            return f"Error: Directory '{directory}' not found."
        matches = [item.name for item in path.glob(pattern) if item.is_file()]
        if not matches:
            return f"No files matched pattern '{pattern}' in '{directory}'."
        return "\n".join(matches)
    except Exception as e:
        return f"Error listing files: {e}"


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*") -> str:
    """Search for pattern across files matching file_pattern
    in the workspace."""
    try:
        matches: list[str] = []
        for file_path in Path(".").rglob(file_pattern):
            if not file_path.is_file():
                continue
            with open(file_path, 'r', encoding='utf-8',
                      errors='replace') as lines:
                for line_num, line in enumerate(lines, start=1):
                    if pattern in line:
                        clean_line = line.rstrip('\r\n')
                        matches.append(f"{file_path}:{line_num}: {clean_line}")
        if not matches:
            return f"No matches found for pattern '{pattern}'"
        return "\n".join(matches)
    except Exception as e:
        return f"Error in files: {e}"


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Search for the definition of a function or class
    across the workspace."""
    try:
        matches: list[str] = []
        for file_path in Path(".").rglob("*.py"):
            if not file_path.is_file():
                continue
            with open(file_path, 'r', encoding='utf-8',
                      errors='replace') as lines:
                for line_num, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    is_func = (
                        stripped.startswith(f"def {name}(")
                        or stripped.startswith(f"def {name} ")
                        or stripped.startswith(f"async def {name}(")
                        or stripped.startswith(f"async def {name} ")
                    )
                    is_class = (
                        stripped.startswith(f"class {name}:")
                        or stripped.startswith(f"class {name}(")
                        or stripped.startswith(f"class {name} ")
                    )
                    if is_func or is_class:
                        clean_line = line.rstrip('\r\n')
                        matches.append(f"{file_path}:{line_num}: {clean_line}")
        if not matches:
            return f"No matches found for function/class '{name}'"
        return "\n".join(matches)
    except Exception as e:
        return f"Error in files: {e}"


@mcp.tool()
def find_references(name: str, filepath: str = "", line: int = 0) -> str:
    """Find all usages and references of a symbol across the workspace."""
    try:
        matches: list[str] = []
        pattern = rf"\b{re.escape(name)}\b"

        for file_path in Path(".").rglob("*.py"):
            if not file_path.is_file():
                continue
            with open(file_path, 'r', encoding='utf-8',
                      errors='replace') as lines:
                for line_num, content_line in enumerate(lines, start=1):
                    if re.search(pattern, content_line):
                        clean_line = content_line.rstrip('\r\n')
                        matches.append(f"{file_path}:{line_num}: {clean_line}")
        if not matches:
            return f"No references found for '{name}'"
        return "\n".join(matches)
    except Exception as e:
        return f"Error in files: {e}"


@mcp.tool()
def run_command(command: str, workdir: str = ".") -> str:
    """Execute a shell command in the specified working directory."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60
        )
        return (f"Exit code: {proc.returncode}\n"
                f"STDOUT: {proc.stdout}\n"
                f"STDERR: {proc.stderr}")
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        return f"Error executing command: {e}"


@mcp.tool()
def get_patch() -> str:
    """Retrieve the unified git diff of all changes made to the repository."""
    try:
        cmd = "git -c core.fileMode=false diff"
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        if proc.returncode == 0:
            return proc.stdout
        return f"Error getting git patch: {proc.stderr}"
    except Exception as e:
        return f"Error getting git patch: {e}"


@mcp.tool()
def run_tests() -> str:
    """Execute the repository evaluation script or test suite."""
    try:
        cmd = os.environ.get("SWE_BENCH_TEST_CMD")
        if not cmd:
            cmd = "bash /eval.sh" if Path('/eval.sh').exists() else "pytest"
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        return (f"Exit code: {proc.returncode}\n"
                f"STDOUT: {proc.stdout}\n"
                f"STDERR: {proc.stderr}")
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 300 seconds."
    except Exception as e:
        return f"Error executing tests: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
