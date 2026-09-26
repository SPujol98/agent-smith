import socket
import tempfile
from pathlib import Path
import pytest

from agent_smith.sandbox.security import (
    BuiltinsGuard,
    FileSystemGuard,
    ImportSecurityValidator,
    NetworkGuard,
    SecurityError,
    validate_code_security,
)

def test_ast_validator_allows_safe_code():
    