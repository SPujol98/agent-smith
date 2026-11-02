from mcp_tools_mbpp import run_tests


def test_run_tests_assertion_success() -> None:
    # Arrange
    code = """
def add(a, b):
    return a + b
"""
    tests = ["assert add(1, 2) == 3", "assert add(-1, 1) == 0"]

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
    tests = ["assert add(1, 2) == 2", "assert add(-1, 1) == 5"]

    # Act
    result = run_tests(code, tests)

    # Assert
    assert isinstance(result, str)
    assert "assertionerror" in result.lower() or "failed" in result.lower()


def test_run_tests_timeout_protection() -> None:
    """Verify that run_tests prevents infinite loops and enforces
    execution timeout."""
    # Arrange: Function containing an infinite loop and assertion list
    candidate_code = "def solution():\n    while True:\n        pass"
    test_list = ["assert solution() == True"]

    # Act: Run tests via MBPP tool signature
    result = run_tests(candidate_code=candidate_code, test_list=test_list)

    # Assert: Must return an explicit timeout observation string
    assert "timeout" in result.lower() or "exceeded" in result.lower()


def test_run_tests_security_restriction() -> None:
    """Verify that run_tests blocks unauthorized module imports
    inside the sandbox."""
    # Arrange: Candidate code attempting an unauthorized system import
    candidate_code = "import os\nos.system('echo hacked')"
    test_list = ["assert True"]

    # Act: Run tests via MBPP tool signature
    result = run_tests(candidate_code=candidate_code, test_list=test_list)

    # Assert: Must catch SecurityError and return a descriptive text
    assert "securityerror" in result.lower() or "not allowed" in result.lower()


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
    result = run_tests(code, tests)

    # Assert
    assert result == "All tests passed successfully."
