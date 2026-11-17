import os
import re
import subprocess
from pathlib import Path, PurePosixPath

from mcp.server.mcpserver import MCPServer

# MCP Server instance
mcp = MCPServer("swebench-tools")

ALLOWED_DIRECTORIES: list[str] = ["/testbed", "/tmp/agent"]
CONTAINER_WORKDIR = "/testbed"
MAX_OUTPUT_CHARS = 10_000


def _exec(
    args: list[str],
    *,
    stdin: str | None = None,
    cwd: str | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """Run a command in the task's container, or locally if there is none.

    The container comes from the SWE_CONTAINER environment variable. Tools
    only build commands; this is the single place that decides where they
    run.
    """
    container = os.environ.get("SWE_CONTAINER")
    if container:
        args = [
            "docker",
            "exec",
            "-i",
            "-w",
            cwd or CONTAINER_WORKDIR,
            container,
            *args,
        ]
        cwd = None
    return subprocess.run(
        args,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        timeout=timeout,
    )


def _resolve_paths(*paths: str | Path) -> list[PurePosixPath]:
    """Canonical absolute paths, resolved where the commands run.

    `realpath -m` follows symlinks and normalises `..` inside the container
    (or locally), and also accepts paths that do not exist yet.
    """
    proc = _exec(["realpath", "-m", "--", *map(str, paths)], timeout=10)
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or "realpath failed")
    return [PurePosixPath(line) for line in proc.stdout.splitlines()]


def _check_path(path: str | Path) -> str | None:
    """Error message if `path` is outside ALLOWED_DIRECTORIES, else None."""
    try:
        target, *allowed = _resolve_paths(path, *ALLOWED_DIRECTORIES)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error: could not resolve path '{path}': {e}"
    if any(target.is_relative_to(directory) for directory in allowed):
        return None
    return (
        f"Error: Access denied: '{path}' (resolved to '{target}') "
        "is outside allowed directories."
    )


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the start and the end of a long text, with a note in between."""
    if len(text) <= limit:
        return text
    half = limit // 2
    omitted = len(text) - 2 * half
    return (
        f"{text[:half]}\n... [{omitted} characters truncated; narrow the "
        f"command, the search or the line range] ...\n{text[-half:]}"
    )


def _read_text(filepath: str) -> str:
    """Content of a file, read where the commands run."""
    proc = _exec(["cat", "--", filepath], timeout=30)
    if proc.returncode != 0:
        raise FileNotFoundError(proc.stderr.strip())
    return proc.stdout


def _format_match(line: str) -> str:
    """Turn grep's 'path:num:text' into the tools' 'path:num text'."""
    path, num, text = line.split(":", 2)
    return f"{path}:{num} {text}"


def _grep(grep_args: list[str], file_pattern: str, no_matches: str) -> str:
    """Search the workspace with grep, where the commands run."""
    try:
        (root,) = _resolve_paths(".")
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error: could not resolve the search root: {e}"
    if err := _check_path(str(root)):
        return err
    command = [
        "grep",
        "-rnIH",
        "--exclude-dir=.git",
        f"--include={file_pattern}",
        *grep_args,
        "--",
        str(root),
    ]
    try:
        proc = _exec(command, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error searching the workspace: {e}"
    if proc.returncode > 1 and not proc.stdout:
        return f"Error searching the workspace: {proc.stderr.strip()}"
    matches = [_format_match(line) for line in proc.stdout.splitlines()]
    return _truncate("\n".join(matches) or no_matches)


def _command_output(proc: subprocess.CompletedProcess[str]) -> str:
    """Exit code, stdout and stderr of a command, for the agent."""
    return (
        f"Exit code: {proc.returncode}\n"
        f"STDOUT: {_truncate(proc.stdout)}\n"
        f"STDERR: {_truncate(proc.stderr)}"
    )


@mcp.tool()
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Read file content with line numbers in cat -n format."""
    if err := _check_path(filepath):
        return err
    try:
        lines = _read_text(filepath).splitlines()
    except FileNotFoundError:
        return f"Error: File '{filepath}' not found."
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error reading file '{filepath}': {e}"
    first = max(1, start_line)
    start = first - 1
    numbered = []
    for num, line in enumerate(lines[start:end_line], start=first):
        numbered.append(f"{num}: {line}")
    return _truncate("\n".join(numbered))


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string."""
    if err := _check_path(filepath):
        return err
    try:
        content = _read_text(filepath)
    except FileNotFoundError:
        return f"Error: File '{filepath}' not found."
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error editing file '{filepath}': {e}"
    if old_str not in content:
        return f"Error: String '{old_str}' not found in '{filepath}'."
    new_content = content.replace(old_str, new_str, 1)
    try:
        proc = _exec(
            ["sh", "-c", 'cat > "$1"', "sh", filepath],
            stdin=new_content,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error editing file '{filepath}': {e}"
    if proc.returncode != 0:
        return f"Error editing file '{filepath}': {proc.stderr.strip()}"
    return f"Successfully updated '{filepath}'."


@mcp.tool()
def list_files(directory: str, pattern: str) -> str:
    """List files in a directory matching a given pattern."""
    if err := _check_path(directory):
        return err
    try:
        proc = _exec(
            [
                "find",
                directory,
                "-maxdepth",
                "1",
                "-type",
                "f",
                "-name",
                pattern,
            ],
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"Error listing files: {e}"
    if proc.returncode != 0:
        return f"Error: Directory '{directory}' not found."
    names = []
    for line in proc.stdout.splitlines():
        names.append(PurePosixPath(line).name)
    names = sorted(names)
    if not names:
        return f"No files matched pattern '{pattern}' in '{directory}'."
    return _truncate("\n".join(names))


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*") -> str:
    """Search for pattern across files matching file_pattern in workspace."""
    return _grep(
        ["-F", "-e", pattern],
        file_pattern,
        f"No matches found for pattern '{pattern}'",
    )


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Search for the definition of a function or class in the workspace."""
    regex = rf"^\s*(async\s+)?(def|class)\s+{re.escape(name)}\b"
    return _grep(
        ["-E", "-e", regex],
        "*.py",
        f"No matches found for function/class '{name}'",
    )


@mcp.tool()
def find_references(name: str, filepath: str = "", line: int = 0) -> str:
    """Find all usages and references of a symbol across the workspace."""
    if filepath:
        if err := _check_path(filepath):
            return err
    return _grep(
        ["-w", "-F", "-e", name],
        "*.py",
        f"No references found for '{name}'",
    )


@mcp.tool()
def run_command(command: str, workdir: str = ".") -> str:
    """Execute a shell command in the specified working directory."""
    if workdir != "." and (err := _check_path(workdir)):
        return err
    try:
        proc = _exec(
            ["sh", "-c", command],
            cwd=None if workdir == "." else workdir,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except OSError as e:
        return f"Error executing command: {e}"
    return _command_output(proc)


@mcp.tool()
def get_patch() -> str:
    """Retrieve the unified git diff of all changes made to the repository."""
    try:
        proc = _exec(["git", "-c", "core.fileMode=false", "diff"], timeout=30)
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"Error getting git patch: {e}"
    if proc.returncode != 0:
        return f"Error getting git patch: {proc.stderr}"
    return proc.stdout


@mcp.tool()
def run_tests() -> str:
    """Execute the repository evaluation script or test suite."""
    command = os.environ.get("SWE_BENCH_TEST_CMD") or (
        "if [ -f /eval.sh ]; then bash /eval.sh; else pytest; fi"
    )
    try:
        proc = _exec(["sh", "-c", command], timeout=300)
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 300 seconds."
    except OSError as e:
        return f"Error executing tests: {e}"
    return _command_output(proc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
