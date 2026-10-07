from pathlib import Path
from mcp_tools_swebench import read_file


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
