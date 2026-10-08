import pytest
import sys

from pathlib import Path
from mcp_tools_swebench import (
    edit_file,
    list_files,
    read_file,
    search_code,
    search_function_or_class_definition_in_code,
    find_references,
    run_command,
    get_patch,
    run_tests
)


def test_read_file_success(tmp_path: Path) -> None:
    # Arrange
    test_file = tmp_path / "sample.py"
    content = "line one\nline two\nline three\nline four\nline five\n"
    test_file.write_text(content, encoding="utf-8")

    # Act
    result = read_file(str(test_file), start_line=2, end_line=4)

    # Assert
    expected_lines = [
        "2: line two",
        "3: line three",
        "4: line four"
    ]
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
    result = edit_file(
        str(test_file), old_str="not_exist", new_str="replace"
    )

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


def test_search_code_success(tmp_path: Path,
                             monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert "foo.py:1:" in result
    assert "bar.py:2:" in result


def test_search_code_no_matches(tmp_path: Path,
                                monkeypatch: pytest.MonkeyPatch) -> None:
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
    # Arrange: files containing class and function definitions
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.py").write_text(
        "class User:\n    def __init__(self):\n        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        "def format_user(user):\n    return str(user)\n",
        encoding="utf-8",
    )

    # Act
    class_result = search_function_or_class_definition_in_code("User")
    func_result = search_function_or_class_definition_in_code("format_user")

    # Assert
    assert "models.py:1:" in class_result
    assert "class User:" in class_result
    assert "utils.py:1:" in func_result
    assert "def format_user(user):" in func_result


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
    # Arrange: create definition file and consumer file
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.py").write_text(
        "class Token:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text(
        "from models import Token\n\ndef get_token():\n    return Token()\n",
        encoding="utf-8",
    )

    # Act: find references to 'Token'
    result = find_references(name="Token", filepath="models.py", line=1)

    # Assert: matches both the definition and usages across the workspace
    assert "models.py:1:" in result
    assert "auth.py:1:" in result
    assert "auth.py:4:" in result


def test_find_references_no_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("x = 10\n", encoding="utf-8")

    # Act
    result = find_references(name="UnknownSymbol")

    # Assert
    assert ("no references" in result.lower()
            or "no matches" in result.lower()
            or result.strip() == "")


def test_run_command_success(tmp_path: Path) -> None:
    """Test valid command execution."""
    # Arrange
    cmd = f'{sys.executable} -c "print(\'hello execution\')"'

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
    cmd = (
        f'{sys.executable} '
        f'-c "print(\'tests passed\')"'
    )
    monkeypatch.setenv("SWE_BENCH_TEST_CMD", cmd)

    # Act
    result = run_tests()

    # Assert
    assert "tests passed" in result
