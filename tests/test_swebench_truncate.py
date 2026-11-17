"""Long tool outputs are truncated before they reach the LLM."""

from pathlib import Path

import pytest

from mcp_tools_swebench import (
    MAX_OUTPUT_CHARS,
    _truncate,
    get_patch,
    run_command,
)


def test_truncate_leaves_short_text_unchanged() -> None:
    # Act / Assert
    assert _truncate("short", limit=10) == "short"


def test_truncate_keeps_start_and_end_of_long_text() -> None:
    # Arrange
    text = "A" * 10 + "M" * 100 + "Z" * 10

    # Act
    result = _truncate(text, limit=20)

    # Assert
    assert result.startswith("A" * 10 + "\n")
    assert result.endswith("\n" + "Z" * 10)
    assert "[100 characters truncated" in result


def test_run_command_truncates_long_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.delenv("SWE_CONTAINER", raising=False)
    size = MAX_OUTPUT_CHARS * 3

    # Act
    result = run_command(f"python3 -c \"print('x' * {size})\"")

    # Assert
    assert "characters truncated" in result
    assert len(result) < MAX_OUTPUT_CHARS * 2


def test_get_patch_is_never_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The patch is the final answer: cutting it would break it."""
    # Arrange
    monkeypatch.delenv("SWE_CONTAINER", raising=False)
    monkeypatch.chdir(tmp_path)
    run_command("git init -q")
    run_command("git config user.email t@t && git config user.name t")
    big = tmp_path / "big.txt"
    big.write_text("old\n", encoding="utf-8")
    run_command("git add big.txt && git commit -qm init")
    big.write_text("new line\n" * MAX_OUTPUT_CHARS, encoding="utf-8")

    # Act
    patch = get_patch()

    # Assert
    assert "characters truncated" not in patch
    assert patch.count("+new line") == MAX_OUTPUT_CHARS
