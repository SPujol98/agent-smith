"""Integration test suite for SandboxRunner orchestration."""

from pathlib import Path
import tempfile
import pytest

from agent_smith.sandbox.runner import SandboxRunner


def test_runner_executes_safe_code() -> None:
    """Ensure SandboxRunner successfully executes benign code and captures state.

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
