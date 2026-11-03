"""Integration test suite for SandboxRunner orchestration."""

import os
import tempfile
from pathlib import Path

import pytest

from agent_smith.config import SandboxConfig
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.sandbox.runner import SandboxRunner
from agent_smith.sandbox.security import SecurityError


def test_runner_executes_safe_code() -> None:
    """Ensure SandboxRunner successfully executes benign code and
    captures state.

    Purpose:
        Verify that benign computation executes within the isolated sandbox
        and exposes the resulting global variables cleanly.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Arrange
        code = "result = sum([1, 2, 3, 4])"
        runner = SandboxRunner(
            allowed_directories=[Path(tmp_dir)],
            authorized_imports=[],
        )

        # Act
        exec_result = runner.run(code)

        # Assert
        assert exec_result.success is True
        assert exec_result.result_env.get("result") == 10


def test_runner_blocks_unauthorized_imports() -> None:
    # Arrange
    code = "import os"
    runner = SandboxRunner(authorized_imports=["math"])

    # Act & Assert
    with pytest.raises(SecurityError):
        runner.run(code)


def test_runner_enforces_filesystem_sandbox() -> None:
    # Arrange
    with (
        tempfile.TemporaryDirectory() as allowed_dir,
        tempfile.TemporaryDirectory() as forbidden_dir,
    ):
        runner = SandboxRunner(allowed_directories=[Path(allowed_dir)])
        target_path = Path(forbidden_dir) / "hack.txt"

        code = f"with open('{target_path}', 'w') as f:\n    f.write('pwned')"

        # Act & Assert
        with pytest.raises((PermissionError, SecurityError)):
            runner.run(code)


def test_runner_allows_filesystem_write_in_permitted_dir() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as allowed_dir:
        runner = SandboxRunner(allowed_directories=[Path(allowed_dir)])
        target_path = Path(allowed_dir) / "output.txt"
        code = f"""
with open(r'{target_path}', 'w') as vault:
    vault.write('valid output')
"""

        # Act
        runner.run(code)

        # Assert
        assert target_path.exists()
        assert target_path.read_text() == "valid output"


def test_runner_blocks_network_access() -> None:
    # Arrange
    runner = SandboxRunner(authorized_imports=["socket"])
    code = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
"""

    # Act & Assert
    with pytest.raises(SecurityError):
        runner.run(code)


def test_runner_returns_execution_result_on_success() -> None:
    # Arrange
    runner = SandboxRunner()
    msg = "hello"
    code = f"""
msg = "{msg}"
print(msg)
"""

    # Act
    result = runner.run(code)

    # Assert
    assert isinstance(result, ExecutionResult)
    assert result.success is True
    assert result.stdout == f"{msg}\n"
    assert result.stderr == ""
    assert result.result_env.get("msg") == msg
    assert result.error is None


def test_runner_captures_runtime_exception_in_result() -> None:
    # Arrange
    runner = SandboxRunner()
    code = """
x = 1 / 0
"""
    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.error is not None
    assert "ZeroDivisionError" in result.error


def test_runner_enforces_execution_timeout() -> None:
    # Arrange
    fast_config = SandboxConfig(max_execution_time_seconds=1)
    runner = SandboxRunner(config=fast_config)
    code = """
while True:
    pass
"""
    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.error is not None
    assert (
        "timed out" in result.error.lower()
        or "timeout" in result.error.lower()
    )


def test_runner_supports_common_python_code() -> None:
    """Ensure typical LLM-generated code runs with the builtins allowlist.

    Purpose:
        Classes, inheritance with super(), common builtins and builtin
        exceptions must be available inside the sandbox.
    """
    # Arrange
    runner = SandboxRunner(authorized_imports=[])
    code = """
class Base:
    def __init__(self, values):
        self.values = values


class Sorter(Base):
    def __init__(self, values):
        super().__init__(values)

    def result(self):
        return sorted(map(abs, self.values))


try:
    assert Sorter([3, -1, 2]).result() == [1, 2, 3]
    raise AssertionError("expected")
except AssertionError as e:
    print(e)
"""

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is True, result.error
    assert result.stdout == "expected\n"


def test_runner_returns_syntax_error_as_result() -> None:
    """Ensure syntax errors are reported to the LLM instead of raised."""
    # Arrange
    runner = SandboxRunner()

    # Act
    result = runner.run("def f(:\n    pass")

    # Assert
    assert result.success is False
    assert result.stdout == ""
    assert result.error is not None
    assert "SyntaxError" in result.error
    assert "^" in result.error


def test_runner_executes_code_in_child_process() -> None:
    """Ensure the code runs in a separate process, not in the agent's."""
    # Arrange
    runner = SandboxRunner(authorized_imports=["os"])

    # Act
    result = runner.run("import os\nchild_pid = os.getpid()")

    # Assert
    assert result.success is True, result.error
    assert result.result_env["child_pid"] != os.getpid()


def test_runner_returns_namespace_after_runtime_error() -> None:
    """Ensure variables created before an error reach the parent, and
    values that cannot be pickled are dropped."""
    # Arrange
    runner = SandboxRunner(authorized_imports=["math"])
    code = """
import math
def helper():
    return 1
before = 42
1 / 0
after = 1
"""

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.result_env["before"] == 42
    assert "after" not in result.result_env
    assert "math" not in result.result_env
    assert "helper" not in result.result_env
