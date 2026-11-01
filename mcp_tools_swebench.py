import os
import re
import subprocess
from pathlib import Path
from typing import Callable

from mcp.server.mcpserver import MCPServer

from agent_smith.sandbox.security import FileSystemGuard, SecurityError

# MCP Server instance
mcp = MCPServer("swebench-tools")

ALLOWED_DIRECTORIES: list[str] = ["/testbed", "/tmp/agent"]


def _check_path(path: str | Path) -> str | None:
    try:
        guard = FileSystemGuard(allowed_directories=ALLOWED_DIRECTORIES)
        guard.validate_path(path)
        return None
    except SecurityError as e:
        return f"Error: {e}"


def _get_search_root() -> tuple[Path | None, str | None]:
    root_path = Path.cwd().resolve()
    if err := _check_path(root_path):
        return None, err
    return root_path, None


def _search_workspace(
    file_pattern: str,
    match_predicate: Callable[[str], bool],
    no_matches_msg: str = "No matches found.",
) -> str:
    root, err = _get_search_root()
    if root is None:
        return err or "Error: Search root path is not allowed."
    guard = FileSystemGuard(allowed_directories=ALLOWED_DIRECTORIES)
    matches: list[str] = []
    for file_path in root.rglob(file_pattern):
        if ".git" in file_path.parts:
            continue
        if not file_path.is_file():
            continue
        try:
            guard.validate_path(file_path)
        except SecurityError:
            continue
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    if match_predicate(line):
                        clean_line = line.rstrip("\r\n")
                        matches.append(
                            f"{file_path.resolve()}: {line_num} {clean_line}"
                        )
        except OSError:
            continue
    if not matches:
        return f"No matches found for pattern '{no_matches_msg}'"
    return "\n".join(matches)


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read file content with line numbers in cat -n format."""
    if err := _check_path(filepath):
        return err
    try:
        with open(
            Path(filepath), "r", encoding="utf-8", errors="replace"
        ) as f:
            lines = f.read().splitlines()
            slice_lines = lines[max(1, start_line) - 1: end_line]
            formatted = [
                f"{num}: {line}"
                for num, line in enumerate(
                    slice_lines, start=max(1, start_line)
                )
            ]
            return "\n".join(formatted)
    except FileNotFoundError:
        return f"Error: File '{filepath}' not found."
    except Exception as e:
        return f"Error: File '{filepath}' not found: {e}."


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string."""
    if err := _check_path(filepath):
        return err
    try:
        path = Path(filepath)
        if not path.is_file():
            return f"Error: File '{filepath}' not found."
        content = path.read_text(encoding="utf-8")
        if old_str not in content:
            return f"Error: String '{old_str}' not found in '{filepath}'."
        new_content = content.replace(old_str, new_str, 1)
        path.write_text(new_content, encoding="utf-8")
        return f"Successfully updated '{filepath}'."
    except Exception as e:
        return f"Error editing file '{filepath}': {e}"


@mcp.tool()
def list_files(directory: str, pattern: str) -> str:
    """List files in a directory matching a given pattern."""
    if err := _check_path(directory):
        return err
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
    """Search for pattern across files matching file_pattern in workspace."""
    return _search_workspace(
        file_pattern=file_pattern,
        match_predicate=lambda line: pattern in line,
        no_matches_msg=f"No matches found for pattern '{pattern}'",
    )


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Search for the definition of a function or class across
    the workspace."""

    def is_definition(line: str) -> bool:
        s = line.strip()
        return (
            s.startswith(f"def {name}(")
            or s.startswith(f"def {name} ")
            or s.startswith(f"async def {name}(")
            or s.startswith(f"async def {name} ")
            or s.startswith(f"class {name}:")
            or s.startswith(f"class {name}(")
            or s.startswith(f"class {name} ")
        )

    return _search_workspace(
        file_pattern="*.py",
        match_predicate=is_definition,
        no_matches_msg=f"No matches found for function/class '{name}'",
    )


@mcp.tool()
def find_references(name: str, filepath: str = "", line: int = 0) -> str:
    """Find all usages and references of a symbol across the workspace."""
    if filepath:
        if err := _check_path(filepath):
            return err

    regex = re.compile(rf"\b{re.escape(name)}\b")
    return _search_workspace(
        file_pattern="*.py",
        match_predicate=lambda testing: bool(regex.search(testing)),
        no_matches_msg=f"No references found for '{name}'",
    )


@mcp.tool()
def run_command(command: str, workdir: str = ".") -> str:
    """Execute a shell command in the specified working directory."""
    if err := _check_path(workdir):
        return err
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return (
            f"Exit code: {proc.returncode}\n"
            f"STDOUT: {proc.stdout}\n"
            f"STDERR: {proc.stderr}"
        )
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
            cmd, shell=True, capture_output=True, text=True, timeout=30
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
            cmd = "bash /eval.sh" if Path("/eval.sh").exists() else "pytest"
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        return (
            f"Exit code: {proc.returncode}\n"
            f"STDOUT: {proc.stdout}\n"
            f"STDERR: {proc.stderr}"
        )
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 300 seconds."
    except Exception as e:
        return f"Error executing tests: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
