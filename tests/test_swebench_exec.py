"""Tests for the executor of the SWE-bench tools (local and container)."""

from pathlib import Path

import pytest

from mcp_tools_swebench import (
    _check_path,
    _exec,
    edit_file,
    find_references,
    get_patch,
    list_files,
    read_file,
    run_command,
    run_tests,
    search_code,
    search_function_or_class_definition_in_code,
)


def test_exec_runs_locally_without_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.delenv("SWE_CONTAINER", raising=False)

    # Act
    result = _exec(["echo", "hello"])

    # Assert
    assert result.returncode == 0
    assert result.stdout == "hello\n"


def test_exec_uses_docker_exec_with_container(fake_docker: Path) -> None:
    # Act
    result = _exec(["echo", "hello"])

    # Assert
    assert result.stdout == "hello\n"
    assert fake_docker.read_text() == (
        "exec -i -w /testbed task-box echo hello\n"
    )


def test_exec_passes_workdir_to_container(
    fake_docker: Path, tmp_path: Path
) -> None:
    # Act
    result = _exec(["pwd"], cwd=str(tmp_path))

    # Assert
    assert f"-w {tmp_path} task-box pwd" in fake_docker.read_text()
    assert result.stdout.strip() == str(tmp_path)


def test_exec_sends_stdin_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.delenv("SWE_CONTAINER", raising=False)

    # Act
    result = _exec(["cat"], stdin="line one\nline two\n")

    # Assert
    assert result.stdout == "line one\nline two\n"


def test_exec_sends_stdin_to_container(fake_docker: Path) -> None:
    # Act
    result = _exec(["cat"], stdin="line one\nline two\n")

    # Assert
    assert result.stdout == "line one\nline two\n"


def test_run_command_runs_inside_container(fake_docker: Path) -> None:
    # Act
    output = run_command("echo from-container")

    # Assert
    assert "Exit code: 0" in output
    assert "from-container" in output
    assert "task-box sh -c echo from-container" in fake_docker.read_text()


def test_get_patch_runs_git_diff_inside_container(fake_docker: Path) -> None:
    # Act
    get_patch()

    # Assert
    assert (
        "-w /testbed task-box git -c core.fileMode=false diff"
        in fake_docker.read_text()
    )


def test_run_tests_checks_eval_script_inside_container(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: run from an empty dir, so the pytest fallback finds nothing
    monkeypatch.delenv("SWE_BENCH_TEST_CMD", raising=False)
    monkeypatch.chdir(tmp_path)

    # Act
    run_tests()

    # Assert
    assert "if [ -f /eval.sh ]" in fake_docker.read_text()


def test_check_path_resolves_inside_container(fake_docker: Path) -> None:
    # Act
    error = _check_path("/testbed/../etc/passwd")

    # Assert
    assert error is not None
    assert "resolved to '/etc/passwd'" in error
    assert "task-box realpath -m -- /testbed/../etc/passwd" in (
        fake_docker.read_text()
    )


def test_check_path_accepts_paths_inside_allowed_dirs(
    fake_docker: Path,
) -> None:
    # Act & Assert
    assert _check_path("/testbed/src/app.py") is None
    assert _check_path("/testbed/new_file_not_created_yet.py") is None


def test_check_path_rejects_symlink_escaping_allowed_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "escape").symlink_to("/etc")
    monkeypatch.delenv("SWE_CONTAINER", raising=False)
    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(allowed)]
    )

    # Act
    error = _check_path(allowed / "escape" / "passwd")

    # Assert
    assert error is not None
    assert "Access denied" in error


def test_file_tools_work_inside_container(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """read/edit/list go through docker exec (the fake runs them locally)."""
    # Arrange
    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(tmp_path)]
    )
    source = tmp_path / "app.py"
    source.write_text("x = 1\ny = 2\n", encoding="utf-8")

    # Act
    edited = edit_file(str(source), "y = 2", "y = 3")
    content = read_file(str(source), start_line=1, end_line=2)
    listing = list_files(str(tmp_path), "*.py")

    # Assert
    assert edited == f"Successfully updated '{source}'."
    assert content == "1: x = 1\n2: y = 3"
    assert listing == "app.py"
    log = fake_docker.read_text()
    assert f"task-box cat -- {source}" in log
    assert f'task-box sh -c cat > "$1" sh {source}' in log
    assert f"task-box find {tmp_path} -maxdepth 1 -type f -name *.py" in log


def test_edit_file_path_cannot_inject_shell_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The path is an argument of sh, never part of the shell script."""
    # Arrange
    monkeypatch.delenv("SWE_CONTAINER", raising=False)
    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(tmp_path)]
    )
    tricky = tmp_path / "a; touch pwned.py"
    tricky.write_text("old\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    # Act
    result = edit_file(str(tricky), "old", "new")

    # Assert
    assert result.startswith("Successfully")
    assert tricky.read_text(encoding="utf-8") == "new\n"
    assert not (tmp_path / "pwned.py").exists()


def test_search_tools_run_grep_inside_container(
    fake_docker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The three searches go through docker exec and skip .git."""
    # Arrange
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "hook.py").write_text("Token\n", encoding="utf-8")
    (repo / "models.py").write_text(
        "class Token:\n    pass\n", encoding="utf-8"
    )
    monkeypatch.setattr("mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(repo)])
    monkeypatch.chdir(repo)

    # Act
    found = search_code("pass", "*.py")
    definition = search_function_or_class_definition_in_code("Token")
    references = find_references("Token")

    # Assert
    assert found == f"{repo}/models.py:2     pass"
    assert definition == f"{repo}/models.py:1 class Token:"
    assert references == f"{repo}/models.py:1 class Token:"
    log = fake_docker.read_text()
    assert "task-box realpath -m -- ." in log
    assert "task-box grep -rnIH --exclude-dir=.git" in log


def test_search_code_pattern_can_start_with_a_dash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-e makes grep read the pattern as a pattern, not as an option."""
    # Arrange
    monkeypatch.delenv("SWE_CONTAINER", raising=False)
    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(tmp_path)]
    )
    (tmp_path / "cli.py").write_text('FLAG = "--verbose"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    # Act
    result = search_code("--verbose", "*.py")

    # Assert
    assert result == f'{tmp_path}/cli.py:1 FLAG = "--verbose"'
