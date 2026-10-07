from mcp_tools_mbpp import run_tests


def test_run_tests_assertion_success() -> None:
    # Arrange
    code = """
def add(a, b):
    return a + b
"""
    tests = [
        "assert add(1, 2) == 3",
        "assert add(-1, 1) == 0"
    ]

    # Act
    result = run_tests(code, tests)

    # Assert
    assert isinstance(result, str)
    assert "passed" in result.lower() or "success" in result.lower()


def test_run_tests_assertion_failure() -> None:
    # Arrange
    code = """
def add(a, b):
    return a - b
"""
    tests = [
        "assert add(1, 2) == 2",
        "assert add(-1, 1) == 5"
    ]

    # Act
    result = run_tests(code, tests)

    # Assert
    assert isinstance(result, str)
    assert "assertionerror" in result.lower() or "failed" in result.lower()
