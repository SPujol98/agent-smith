"""Integration test suite for SandboxRunner orchestration."""

import os
import tempfile
import threading
from pathlib import Path

import pytest

from agent_smith.config import SandboxConfig
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.sandbox.runner import SandboxRunner


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

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("SecurityError")


def test_runner_enforces_filesystem_sandbox() -> None:
    # Arrange
    with (
        tempfile.TemporaryDirectory() as allowed_dir,
        tempfile.TemporaryDirectory() as forbidden_dir,
    ):
        runner = SandboxRunner(allowed_directories=[Path(allowed_dir)])
        target_path = Path(forbidden_dir) / "hack.txt"

        code = f"with open('{target_path}', 'w') as f:\n    f.write('pwned')"

        # Act
        result = runner.run(code)

        # Assert
        assert result.success is False
        assert result.error is not None
        assert "SecurityError" in result.error
        assert not target_path.exists()


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

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.error is not None
    assert "SecurityError" in result.error


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


def _run_with_deadline(
    runner: SandboxRunner, code: str, deadline: float = 10
) -> ExecutionResult | None:
    """Run code in a worker thread; return None if it is still running
    after the deadline (so a broken timeout fails the test, not hangs it)."""
    results: list[ExecutionResult] = []
    worker = threading.Thread(
        target=lambda: results.append(runner.run(code)), daemon=True
    )
    worker.start()
    worker.join(timeout=deadline)
    return results[0] if results else None


def test_runner_timeout_cannot_be_caught_by_user_code() -> None:
    """Ensure user code cannot catch the timeout and keep running."""
    # Arrange
    runner = SandboxRunner(config=SandboxConfig(max_execution_time_seconds=1))
    code = """
while True:
    try:
        while True:
            pass
    except BaseException:
        pass
"""

    # Act
    result = _run_with_deadline(runner, code)

    # Assert
    assert result is not None, "timeout was caught: code kept running"
    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("TimeoutError")


def test_runner_timeout_works_outside_main_thread() -> None:
    """Ensure the timeout does not rely on signals (main thread only)."""
    # Arrange
    runner = SandboxRunner(config=SandboxConfig(max_execution_time_seconds=1))

    # Act
    result = _run_with_deadline(runner, "while True:\n    pass")

    # Assert
    assert result is not None
    assert result.error is not None
    assert result.error.startswith("TimeoutError")


def test_runner_keeps_partial_output_on_timeout() -> None:
    """Ensure output printed before a timeout reaches the LLM."""
    # Arrange
    runner = SandboxRunner(
        authorized_imports=["sys"],
        config=SandboxConfig(max_execution_time_seconds=1),
    )
    code = """
import sys
print("before the loop")
print("warning", file=sys.stderr)
while True:
    pass
"""

    # Act
    result = _run_with_deadline(runner, code)

    # Assert
    assert result is not None
    assert result.success is False
    assert result.stdout == "before the loop\n"
    assert result.stderr == "warning\n"
    assert result.error is not None
    assert result.error.startswith("TimeoutError")
    assert "partial" in result.error


def test_runner_enforces_memory_limit() -> None:
    """Ensure code cannot allocate more than max_memory_mb."""
    # Arrange
    runner = SandboxRunner(config=SandboxConfig(max_memory_mb=50))
    code = "data = bytearray(200 * 1024 * 1024)"

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("MemoryError")


def test_runner_memory_limit_allows_normal_allocations() -> None:
    """Ensure the limit leaves room for allocations below max_memory_mb."""
    # Arrange
    runner = SandboxRunner(config=SandboxConfig(max_memory_mb=50))
    code = "data = bytearray(10 * 1024 * 1024)\nsize = len(data)"

    # Act
    result = runner.run(code)

    # Assert
    assert result.success is True, result.error
    assert result.result_env["size"] == 10 * 1024 * 1024


def test_runner_reports_child_that_dies_without_result() -> None:
    """Ensure a child that exits without sending a result is reported."""
    # Arrange
    runner = SandboxRunner(authorized_imports=["os"])

    # Act
    result = runner.run("import os\nprint('bye')\nos._exit(3)")

    # Assert
    assert result.success is False
    assert result.stdout == "bye\n"
    assert result.error is not None
    assert "terminated unexpectedly" in result.error
    assert "exit code 3" in result.error


def test_runner_propagates_system_exit() -> None:
    """Ensure SystemExit from the code reaches the caller (agent loop)."""
    # Arrange
    runner = SandboxRunner()

    # Act & Assert
    with pytest.raises(SystemExit) as exc_info:
        runner.run("raise SystemExit(3)")
    assert exc_info.value.code == 3


def test_runner_propagates_keyboard_interrupt() -> None:
    """Ensure KeyboardInterrupt from the code reaches the caller."""
    # Arrange
    runner = SandboxRunner()

    # Act & Assert
    with pytest.raises(KeyboardInterrupt):
        runner.run("raise KeyboardInterrupt")
