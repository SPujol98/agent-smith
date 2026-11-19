"""The SWE-bench tools find the repository through TESTBED_PATH."""

from pathlib import Path

import pytest

from mcp_tools_swebench import (
    get_patch,
    read_file,
    run_command,
    search_code,
)


@pytest.fixture
def testbed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository in TESTBED_PATH, with the server started elsewhere."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.delenv("SWE_CONTAINER", raising=False)
    monkeypatch.setenv("TESTBED_PATH", str(repo))
    monkeypatch.chdir(elsewhere)
    return repo


def test_files_in_testbed_path_are_allowed(testbed: Path) -> None:
    """TESTBED_PATH is accepted even if it is not in ALLOWED_DIRECTORIES."""
    # Act
    absolute = read_file(str(testbed / "src" / "app.py"), 1, 1)
    relative = read_file("src/app.py", 1, 1)

    # Assert
    assert absolute == "1: x = 1"
    assert relative == "1: x = 1"


def test_paths_outside_testbed_path_are_denied(testbed: Path) -> None:
    # Act
    result = read_file(str(testbed.parent / "elsewhere" / "a.py"), 1, 1)

    # Assert
    assert result.startswith("Error: Access denied")


def test_commands_and_searches_run_in_testbed_path(testbed: Path) -> None:
    # Act
    pwd = run_command("pwd")
    in_src = run_command("ls", workdir="src")
    found = search_code("x = 1", "*.py")

    # Assert
    assert f"STDOUT: {testbed}\n" in pwd
    assert "app.py" in in_src
    assert found == f"{testbed}/src/app.py:1 x = 1"


def test_get_patch_diffs_the_testbed_repository(testbed: Path) -> None:
    # Arrange
    run_command("git init -q")
    run_command("git config user.email t@t && git config user.name t")
    run_command("git add -A && git commit -qm init")
    (testbed / "src" / "app.py").write_text("x = 2\n", encoding="utf-8")

    # Act
    patch = get_patch()

    # Assert
    assert "-x = 1" in patch
    assert "+x = 2" in patch
