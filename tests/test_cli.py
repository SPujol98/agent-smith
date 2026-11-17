"""Tests for the interactive sandbox (uv run sandbox)."""

from collections.abc import Callable, Iterable

import pytest

from agent_smith.sandbox.cli import parse_args, read_snippet, repl
from agent_smith.sandbox.runner import SandboxRunner


def fake_input(lines: Iterable[str]) -> Callable[[str], str]:
    """An input() that returns the given lines, then raises EOFError."""
    pending = iter(lines)

    def read(prompt: str) -> str:
        try:
            return next(pending)
        except StopIteration:
            raise EOFError from None

    return read


def test_parse_args_reads_config_and_mcp_options() -> None:
    # Act
    args = parse_args(["conf.json", "--mcp-stdio", "python tools.py"])

    # Assert
    assert str(args.config) == "conf.json"
    assert args.mcp_stdio == "python tools.py"
    assert args.mcp_server is None


def test_parse_args_rejects_both_mcp_options() -> None:
    # Act / Assert
    with pytest.raises(SystemExit):
        parse_args(["--mcp-stdio", "x", "--mcp-server", "http://h/mcp"])


def test_read_snippet_reads_until_an_empty_line() -> None:
    # Arrange
    read = fake_input(["import math", "x = math.sqrt(4)", "", "other"])

    # Act
    snippet = read_snippet(read)

    # Assert
    assert snippet == "import math\nx = math.sqrt(4)\n"


def test_read_snippet_returns_exit_at_once() -> None:
    # Arrange
    read = fake_input(["exit", "never read"])

    # Act / Assert
    assert read_snippet(read) == "exit"


def test_repl_runs_each_snippet_in_a_fresh_sandbox(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    read = fake_input(
        ["x = 20", "", "print(x + 1)", "", "exit", "print('no')", ""]
    )

    # Act
    repl(SandboxRunner(), read)

    # Assert
    output = capsys.readouterr()
    assert "NameError" in output.err
    assert output.out == ""


def test_repl_reports_errors_and_goes_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange
    read = fake_input(
        ["import os", "", "1 / 0", "", "print('still here')", ""]
    )

    # Act
    repl(SandboxRunner(), read)

    # Assert
    output = capsys.readouterr()
    assert "SecurityError" in output.err
    assert "ZeroDivisionError" in output.err
    assert "still here" in output.out


def test_repl_prints_final_answer(capsys: pytest.CaptureFixture[str]) -> None:
    # Arrange
    read = fake_input(["final_answer(42)", ""])

    # Act
    repl(SandboxRunner(), read)

    # Assert
    assert "Final answer: 42" in capsys.readouterr().out
