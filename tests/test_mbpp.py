"""The MBPP run_tests tool, as the subject defines it."""

import json
from typing import Any

from mcp_tools_mbpp import run_tests


def _report(code: str, tests: list[str], **kwargs: Any) -> dict[str, Any]:
    """Call run_tests and parse its JSON answer."""
    report: dict[str, Any] = json.loads(run_tests(code, tests, **kwargs))
    return report


def test_run_tests_returns_json_with_success_and_output() -> None:
    # Arrange
    code = "def add(a, b):\n    return a + b"
    tests = ["assert add(1, 2) == 3", "assert add(-1, 1) == 0"]

    # Act
    report = _report(code, tests)

    # Assert
    assert report == {"success": True, "output": "All tests passed."}


def test_run_tests_reports_a_failed_assertion() -> None:
    # Arrange
    code = "def add(a, b):\n    return a - b"
    tests = ["assert add(1, 2) == 3"]

    # Act
    report = _report(code, tests)

    # Assert
    assert report["success"] is False
    assert "AssertionError" in report["output"]


def test_run_tests_keeps_what_the_code_prints() -> None:
    # Arrange
    code = "def f():\n    print('debug')\n    return 1"
    tests = ["assert f() == 2"]

    # Act
    report = _report(code, tests)

    # Assert
    assert report["success"] is False
    assert report["output"].startswith("debug\n")


def test_run_tests_accepts_the_subject_keyword_names() -> None:
    """The moulinette may call it as run_tests(code=..., test_list=...)."""
    # Act
    raw = run_tests(code="x = 1", test_list=["assert x == 1"])

    # Assert
    assert json.loads(raw)["success"] is True


def test_run_tests_uses_test_imports() -> None:
    # Arrange
    code = "def root(x):\n    return math.sqrt(x)"
    tests = ["assert root(9) == 3"]

    # Act
    report = _report(code, tests, test_imports=["import math"])

    # Assert
    assert report["success"] is True


def test_run_tests_stops_infinite_loops() -> None:
    # Arrange
    code = "def solution():\n    while True:\n        pass"
    tests = ["assert solution() is True"]

    # Act
    report = _report(code, tests)

    # Assert
    assert report["success"] is False
    assert "TimeoutError" in report["output"]


def test_run_tests_blocks_unauthorized_imports() -> None:
    # Arrange
    code = "import os\nos.system('echo hacked')"
    tests = ["assert True"]

    # Act
    report = _report(code, tests)

    # Assert
    assert report["success"] is False
    assert "SecurityError" in report["output"]


def test_run_tests_accepts_solution_using_common_builtins() -> None:
    """Ensure normal MBPP solutions (sorted, classes...) pass run_tests."""
    # Arrange
    code = """
class Pair:
    def __init__(self, a, b):
        self.a, self.b = a, b


def sort_desc(values):
    return sorted(values, reverse=True)
"""
    tests = [
        "assert sort_desc([1, 3, 2]) == [3, 2, 1]",
        "assert Pair(1, 2).b == 2",
    ]

    # Act
    report = _report(code, tests)

    # Assert
    assert report["success"] is True
