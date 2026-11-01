import sys
from pathlib import Path

import pytest

from mcp_tools_swebench import (
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


@pytest.fixture(autouse=True)
def configure_test_allowed_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configure ALLOWED_DIRECTORIES globally for unit tests.

    Purpose:
        Allow Pytest's temporary execution directories (tmp_path and /tmp)
        to be recognized as authorized zones, enabling functional tool
        tests to run safely on the host machine.
    """
    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES",
        ["/testbed", "/tmp/agent", str(tmp_path), "/tmp"],
    )


def test_read_file_success(tmp_path: Path) -> None:
    # Arrange
    test_file = tmp_path / "sample.py"
    content = "line one\nline two\nline three\nline four\nline five\n"
    test_file.write_text(content, encoding="utf-8")

    # Act
    result = read_file(str(test_file), start_line=2, end_line=4)

    # Assert
    expected_lines = ["2: line two", "3: line three", "4: line four"]
    assert "\n".join(expected_lines) == result.strip()
    assert "line one" not in result
    assert "line five" not in result


def test_read_file_not_found() -> None:
    # Arrange
    inexistent_path = "/rute/dummy.py"

    # Act
    result = read_file(inexistent_path, start_line=1, end_line=5)

    # Assert
    assert isinstance(result, str)
    assert "error" in result.lower() or "not found" in result.lower()


def test_edit_file_success(tmp_path: Path) -> None:
    # Arrange
    test_file = tmp_path / "greeting.py"
    test_file.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    # Act
    result = edit_file(str(test_file), old_str="'hi'", new_str="'bye'")

    # Assert
    assert "success" in result.lower() or "updated" in result.lower()
    assert test_file.read_text(encoding="utf-8") == (
        "def hello():\n    return 'bye'\n"
    )


def test_edit_file_string_not_found(tmp_path: Path) -> None:
    # Arrange
    test_file = tmp_path / "greeting.py"
    content = "def hello():\n    return 'hi'\n"
    test_file.write_text(content, encoding="utf-8")

    # Act
    result = edit_file(str(test_file), old_str="not_exist", new_str="replace")

    # Assert
    assert "not found" in result.lower() or "error" in result.lower()
    assert test_file.read_text(encoding="utf-8") == content


def test_edit_file_file_not_found(tmp_path: Path) -> None:
    # Arrange & Act
    result = edit_file("/ruta/inexistent.py", old_str="a", new_str="b")

    # Assert
    assert "error" in result.lower() or "not found" in result.lower()


def test_list_files_success(tmp_path: Path) -> None:
    # Arrange: create sample files in a directory
    sub_dir = tmp_path / "src"
    sub_dir.mkdir()
    (sub_dir / "main.py").write_text("# main", encoding="utf-8")
    (sub_dir / "utils.py").write_text("# utils", encoding="utf-8")
    (sub_dir / "notes.txt").write_text("notes", encoding="utf-8")

    # Act: list files matching pattern *.py
    result = list_files(str(sub_dir), "*.py")

    # Assert
    assert "main.py" in result
    assert "utils.py" in result
    assert "notes.txt" not in result


def test_list_files_dir_not_found() -> None:
    # Act: query a non-existent directory
    result = list_files("/non/existent/directory", "*.py")

    # Assert: graceful error handling
    assert "error" in result.lower() or "not found" in result.lower()


def test_search_code_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: set up temporary workspace with test files
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text(
        "def ping():\n    return 'pong'\n", encoding="utf-8"
    )
    (tmp_path / "bar.py").write_text(
        "def test():\n    ping()\n", encoding="utf-8"
    )

    # Act: search for occurrences of 'ping'
    result = search_code(pattern="ping", file_pattern="*.py")

    # Assert: verify grep -n style output
    assert "foo.py: 1 def ping():" in result
    assert "bar.py: 2     ping()" in result


def test_search_code_no_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: workspace without target string
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("x = 42\n", encoding="utf-8")

    # Act
    result = search_code(pattern="not_found", file_pattern="*.py")

    # Assert: descriptive feedback when no matches exist
    assert (
        "no matches" in result.lower()
        or result.strip() == ""
        or "0 matches" in result.lower()
    )


def test_search_definition_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    models_file = tmp_path / "models.py"
    utils_file = tmp_path / "utils.py"

    models_file.write_text("class User:\n    pass\n", encoding="utf-8")
    utils_file.write_text(
        "def format_user(user):\n    pass\n", encoding="utf-8"
    )

    class_result = search_function_or_class_definition_in_code("User")
    func_result = search_function_or_class_definition_in_code("format_user")

    # Assert: Verifica que la ruta absoluta esté presente y coincida
    assert f"{models_file.resolve()}: 1 class User:" in class_result
    assert f"{utils_file.resolve()}: 1 def format_user(user):" in func_result


def test_search_definition_no_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.py").write_text("x = 42\n", encoding="utf-8")

    # Act
    result = search_function_or_class_definition_in_code("non_existent")

    # Assert
    assert "no matches" in result.lower() or result.strip() == ""


def test_find_references_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    models_file = tmp_path / "models.py"
    auth_file = tmp_path / "auth.py"

    models_file.write_text("class Token:\n    pass\n", encoding="utf-8")
    auth_file.write_text(
        "from models import Token\n\ndef get_token():\n    return Token()\n",
        encoding="utf-8",
    )

    result = find_references(name="Token", filepath="models.py", line=1)

    assert f"{models_file.resolve()}: 1 class Token:" in result
    assert f"{auth_file.resolve()}: 1 from models import Token" in result
    assert f"{auth_file.resolve()}: 4     return Token()" in result


def test_find_references_no_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("x = 10\n", encoding="utf-8")

    # Act
    result = find_references(name="UnknownSymbol")

    # Assert
    assert (
        "no references" in result.lower()
        or "no matches" in result.lower()
        or result.strip() == ""
    )


def test_run_command_success(tmp_path: Path) -> None:
    """Test valid command execution."""
    # Arrange
    cmd = f"{sys.executable} -c \"print('hello execution')\""

    # Act
    output = run_command(command=cmd, workdir=str(tmp_path))

    # Assert
    assert "hello execution" in output
    assert "0" in output


def test_run_command_exit_code_failure(tmp_path: Path) -> None:
    """Test command failure and exit code reporting."""
    # Arrange
    cmd = f'{sys.executable} -c "import sys; sys.exit(42)"'

    # Act
    output = run_command(command=cmd, workdir=str(tmp_path))

    # Assert
    assert "42" in output


def test_get_patch_invokes_git_diff() -> None:
    """Test get_patch string output."""
    # Arrange & Act
    result = get_patch()

    # Assert
    assert isinstance(result, str)


def test_run_tests_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test test suite execution via environment variable."""
    # Arrange
    cmd = f"{sys.executable} -c \"print('tests passed')\""
    monkeypatch.setenv("SWE_BENCH_TEST_CMD", cmd)

    # Act
    result = run_tests()

    # Assert
    assert "tests passed" in result


def test_read_file_unauthorized_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure reading a file outside allowed directories is blocked.

    Purpose:
        Verify that read_file validates the canonical filepath against
        ALLOWED_DIRECTORIES and returns a graceful error message when access
        to an unauthorized filesystem path is attempted.
    """
    # Arrange
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    forbidden_file = tmp_path / "forbidden.py"
    forbidden_file.write_text("secret_data = 123\n", encoding="utf-8")

    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(allowed_dir)]
    )

    # Act
    result = read_file(str(forbidden_file), start_line=1, end_line=5)

    # Assert
    assert (
        "error" in result.lower()
        or "access denied" in result.lower()
        or "unauthorized" in result.lower()
    )


def test_edit_file_unauthorized_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure editing a file outside allowed directories is rejected.

    Purpose:
        Verify that edit_file prevents modifications to files outside
        ALLOWED_DIRECTORIES, preserving original file contents and returning an
        error message to the caller.
    """
    # Arrange
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    forbidden_file = tmp_path / "forbidden.py"
    original_content = "var = 1\n"
    forbidden_file.write_text(original_content, encoding="utf-8")

    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(allowed_dir)]
    )

    # Act
    result = edit_file(str(forbidden_file), old_str="1", new_str="2")

    # Assert
    assert (
        "error" in result.lower()
        or "access denied" in result.lower()
        or "unauthorized" in result.lower()
    )
    assert forbidden_file.read_text(encoding="utf-8") == original_content


def test_list_files_unauthorized_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    forbidden_dir = tmp_path / "forbidden"
    forbidden_dir.mkdir()
    (forbidden_dir / "secret.py").write_text("# secret", encoding="utf-8")

    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(allowed_dir)]
    )

    # Act
    result = list_files(str(forbidden_dir), "*.py")

    # Assert
    assert (
        "error" in result.lower()
        or "access denied" in result.lower()
        or "unauthorized" in result.lower()
    )


def test_run_command_unauthorized_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure shell command execution in unauthorized directories is blocked.

    Purpose:
        Verify that run_command validates the requested working directory
        against ALLOWED_DIRECTORIES before spawning a subprocess, returning an
        error message if the path is unauthorized.
    """
    # Arrange
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    forbidden_dir = tmp_path / "forbidden"
    forbidden_dir.mkdir()

    monkeypatch.setattr(
        "mcp_tools_swebench.ALLOWED_DIRECTORIES", [str(allowed_dir)]
    )

    # Act
    result = run_command("ls", workdir=str(forbidden_dir))

    # Assert
    assert (
        "error" in result.lower()
        or "access denied" in result.lower()
        or "unauthorized" in result.lower()
    )
