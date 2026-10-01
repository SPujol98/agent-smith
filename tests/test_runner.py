"""Integration test suite for SandboxRunner orchestration."""

from pathlib import Path
import tempfile
import pytest

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
        execution_env = runner.run(code)

        # Assert
        assert execution_env.get("result") == 10


def test_runner_blocks_unauthorized_imports() -> None:
    # Arrange
    code = "import os"
    runner = SandboxRunner(authorized_imports=["math"])

    # Act & Assert
    with pytest.raises(SecurityError):
        runner.run(code)


def test_runner_enforces_filesystem_sandbox() -> None:
    # Arrange
    with (tempfile.TemporaryDirectory() as allowed_dir,
          tempfile.TemporaryDirectory() as forbidden_dir):

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
        assert target_path.read_text() == 'valid output'


def test_runner_blocks_network_access() -> None:
    # Arrange
    runner = SandboxRunner(authorized_imports=["socket"])
    code = """
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
"""

    # Act & Assert
    with pytest.raises(SecurityError):
        runner.run(code)
