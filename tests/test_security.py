"""Security test suite for the Agent_Smith execution sandbox.

This module validates that the sandbox enforces strict isolation across:
1. Static code analysis (AST validation of imports and dynamic calls).
2. Filesystem boundaries (directory restriction and traversal prevention).
3. Runtime built-in namespace sanitization.
4. Network isolation (blocking outbound sockets and ensuring
state restoration).
"""

from pathlib import Path
import socket
import tempfile
import pytest

from agent_smith.sandbox.security import (
    BuiltinsGuard,
    FileSystemGuard,
    NetworkGuard,
    SecurityError,
    validate_code_security,
)


def test_ast_validator_allows_safe_code() -> None:
    """Ensure safe Python code with whitelisted imports passes AST validation.

    Purpose:
        Verify that benign code does not trigger false positives when its
        imported modules are explicitly present in the authorized imports list.
    """
    # Arrange
    safe_code = """
import math

def calculate_area(radius):
    return math.pi * (radius ** 2)

result = calculate_area(5)
"""
    authorized_imports = ["math"]

    # Act & Assert
    # If no SecurityError is raised, the validation succeeded as expected.
    validate_code_security(safe_code, authorized_imports)


def test_ast_validator_blocks_forbidden_imports() -> None:
    """Ensure scripts attempting to import unauthorized modules are blocked.

    Purpose:
        Verify that the AST visitor catches non-whitelisted modules
        (such as 'subprocess') and immediately raises a SecurityError before
        the code reaches the runtime engine.
    """
    # Arrange
    forbidden_code = """
from subprocess import Popen
"""
    authorized_imports = ["math"]

    # Act & Assert
    with pytest.raises(SecurityError):
        validate_code_security(forbidden_code, authorized_imports)


def test_ast_validator_blocks_eval_exec() -> None:
    """Ensure direct invocations of 'eval' and 'exec' are blocked
    at parse time.

    Purpose:
        Prevent arbitrary dynamic code evaluation. The AST visitor inspects
        Call nodes and rejects any invocation of dangerous
        meta-programming primitives.
    """
    # Arrange
    eval_code = "eval('1 + 1')"
    exec_code = "exec('x = 42')"
    authorized_imports = ["math"]

    # Act & Assert
    with pytest.raises(SecurityError):
        validate_code_security(eval_code, authorized_imports)

    with pytest.raises(SecurityError):
        validate_code_security(exec_code, authorized_imports)


def test_filesystem_guard_allows_safe_path() -> None:
    """Ensure file operations inside the authorized directory succeed.

    Purpose:
        Verify that FileSystemGuard allows opening and reading files
        that reside strictly within the designated sandbox folder.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_dir:
        guard = FileSystemGuard(allowed_directories=[tmp_dir])
        test_file = Path(tmp_dir) / "sample.txt"
        test_file.write_text("hello sandbox")

        # Act
        with guard.open(test_file, "r") as f:
            content = f.read()

        # Assert
        assert content == "hello sandbox"


def test_filesystem_guard_blocks_traversal() -> None:
    """Ensure directory traversal attacks (e.g., using '../') are blocked.

    Purpose:
        Verify that canonical path resolution detects relative escapes
        attempting to access parent directories outside the allowed boundaries.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_dir:
        guard = FileSystemGuard(allowed_directories=[tmp_dir])
        traversal_path = Path(tmp_dir) / ".." / "secret.txt"

        # Act & Assert
        with pytest.raises(SecurityError):
            guard.open(traversal_path, "r")


def test_builtins_guard_sanitizes_namespace() -> None:
    """Ensure hazardous built-in functions are removed while safe utilities
    remain.

    Purpose:
        Verify that the execution namespace is stripped of hazardous primitives
        like '__import__', 'eval', and 'exec', while preserving standard
        utilities (like 'len' and 'range') alongside the guarded 'open'
        implementation.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as tmp_dir:
        fs_guard = FileSystemGuard(allowed_directories=[tmp_dir])
        guard = BuiltinsGuard(file_system_guard=fs_guard)

        # Act
        safe_builtins = guard.build_builtins()

        # Assert: Dangerous primitives are banned
        assert "eval" not in safe_builtins
        assert "exec" not in safe_builtins
        assert "__import__" not in safe_builtins

        # Assert: Essential safe utilities remain available
        assert "len" in safe_builtins
        assert "range" in safe_builtins
        assert "open" in safe_builtins


def test_network_guard_blocks_sockets() -> None:
    """Ensure outbound network socket creation is intercepted
    within the sandbox.

    Purpose:
        Verify that entering the NetworkGuard context patches 'socket.socket'
        so any attempt to initialize a network endpoint raises a SecurityError.
    """
    # Arrange & Act & Assert
    with NetworkGuard():
        with pytest.raises(SecurityError):
            socket.socket()


def test_network_guard_restores_socket() -> None:
    """Ensure native socket capabilities are restored after
    exiting NetworkGuard.

    Purpose:
        Verify that the context manager cleanly restores the original
        'socket.socket' constructor upon exit, preventing side effects on the
        host process or other tests.
    """
    # Arrange & Act
    with NetworkGuard():
        pass

    # Assert: Default socket creation works normally again
    s = socket.socket()
    assert s is not None
    s.close()
