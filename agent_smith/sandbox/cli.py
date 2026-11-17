import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from agent_smith.config import SandboxConfig
from agent_smith.sandbox.mcp_client import MCPConnectionError
from agent_smith.sandbox.runner import SandboxRunner

DEFAULT_TEMPLATE = Path("sandbox_template.json")
EXIT_COMMANDS = frozenset({"exit", "quit", "exit()", "quit()"})


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Command line options of `uv run sandbox`."""
    parser = argparse.ArgumentParser(
        prog="sandbox", description="Interactive Agent Smith sandbox."
    )
    parser.add_argument(
        "config", nargs="?", type=Path, help="JSON configuration file"
    )
    mcp = parser.add_mutually_exclusive_group()
    mcp.add_argument(
        "--mcp-stdio", metavar="COMMAND", help="start an MCP server (stdio)"
    )
    mcp.add_argument(
        "--mcp-server", metavar="URL", help="connect to an MCP server (HTTP)"
    )
    return parser.parse_args(argv)


def read_snippet(read: Callable[[str], str] = input) -> str:
    """Read lines until an empty one; exit and quit end at once."""
    lines = [read(">>> ")]
    if lines[0].strip() in EXIT_COMMANDS:
        return lines[0]
    while lines[-1].strip():
        lines.append(read("... "))
    return "\n".join(lines)


def repl(runner: SandboxRunner, read: Callable[[str], str] = input) -> None:
    """Read, run and print snippets until exit, quit or Ctrl+D.

    Each snippet runs in a fresh sandbox, like each step of the agent.
    """
    while True:
        try:
            code = read_snippet(read)
        except EOFError:
            print()
            return
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
            continue
        if code.strip() in EXIT_COMMANDS:
            return
        if not code.strip():
            continue
        try:
            result = runner.run(code)
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
            continue
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        if result.error:
            print(result.error.rstrip(), file=sys.stderr)
        if result.is_finished:
            print(f"Final answer: {result.final_answer_value}")


def load_configuration(path: Path | None = None) -> SandboxConfig:
    """The given config file, else the default template (created if needed)."""
    if path is not None:
        return SandboxConfig.from_file(path)
    if DEFAULT_TEMPLATE.exists():
        return SandboxConfig.from_file(DEFAULT_TEMPLATE)
    config = SandboxConfig()
    config.save_template(DEFAULT_TEMPLATE)
    return config


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_configuration(args.config)
    try:
        with SandboxRunner(
            config=config, mcp_stdio=args.mcp_stdio, mcp_url=args.mcp_server
        ) as runner:
            print("=== Agent Smith Sandbox ===")
            print(runner.manual)
            print("An empty line runs the code; exit or Ctrl+D leaves.")
            repl(runner)
    except MCPConnectionError as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
