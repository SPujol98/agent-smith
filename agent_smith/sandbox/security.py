import ast
import builtins
import socket
from pathlib import Path
from typing import Callable, Any
from types import TracebackType

_real_open = builtins.open


class SecurityError(Exception):
    """Exception raised when code violates sandbox security policies."""
    pass


class ImportSecurityValidator(ast.NodeVisitor):
    """AST visitor that validates imports against an allowlist."""
    RESTRICTED_CALLS = {"__import__", "eval", "exec", "compile"}

    def __init__(self, authorized_imports: list[str]) -> None:
        super().__init__()
        self.authorized_imports = authorized_imports

    def _is_module_allowed(self, module_name: str) -> bool:
        """Check if a module name matches the authorized imports allowlist."""
        for pattern in self.authorized_imports:
            if pattern == module_name:
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if (prefix == module_name or
                        module_name.startswith(f"{prefix}.")):
                    return True
        return False

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if not self._is_module_allowed(alias.name):
                raise SecurityError("Unauthorized import detected: "
                                    f"'{alias.name}' (line {node.lineno})")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level > 0:
            raise SecurityError("Relative imports not allowed")
        if node.level == 0:
            if node.module and not self._is_module_allowed(node.module):
                raise SecurityError(f"{node.module} is a forbidden module.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Intercept dangerous direct calls to restricted functions."""
        if (isinstance(node.func, ast.Name) and
                node.func.id in self.RESTRICTED_CALLS):
            raise SecurityError(f"Forbidden call to '{node.func.id}()' "
                                f"detected (line {node.lineno})")
        self.generic_visit(node)


class FileSystemGuard:
    """Enforces directory boundary constraints and safe file operations."""
    def __init__(self, allowed_directories: list[str | Path]) -> None:
        self.allowed_directories = self._normalize_paths(allowed_directories)

    def _normalize_paths(self, directories: list[str | Path]) -> list[Path]:
        """Convert input paths to canonical absolute Path instances."""
        return [Path(d).resolve() for d in directories]

    def validate_path(self, path: str | Path) -> Path:
        """Resolve and verify if a path falls strictly within
         allowed boundaries."""
        target = Path(path).resolve()
        for allowed_dir in self.allowed_directories:
            if target.is_relative_to(allowed_dir):
                return target
        raise SecurityError(f"Access denied: '{path}' (resolved to '{target}')"
                            " is outside allowed directories.")

    def open(self, file: str | Path, *args: Any, **kwargs: Any) -> Any:
        """Safely open a file after validating its target directory."""
        target = self.validate_path(file)
        return _real_open(target, *args, **kwargs)


class BuiltinsGuard:
    """Constructs a sanitized execution builtins dictionary."""

    DEFAULT_RESTRICTED: set[str] = {
        "eval",
        "exec",
        "compile",
        "__import__",
    }

    def __init__(self, file_system_guard: FileSystemGuard,
                 restricted_builtins: set[str] | None = None) -> None:
        self.fs_guard = file_system_guard
        self.restricted = restricted_builtins or self.DEFAULT_RESTRICTED

    def build_builtins(self) -> dict[str, Any]:
        """Generate a safe copy of builtins with
        restricted primitives removed."""
        safe_builtins = builtins.__dict__.copy()
        for restrict in self.restricted:
            safe_builtins.pop(restrict, None)
        safe_builtins["open"] = self.fs_guard.open
        return safe_builtins


class NetworkGuard:
    """Enforces network isolation by intercepting socket creation."""
    def __init__(self, allow_network: bool = False) -> None:
        self.allow_network = allow_network
        self._real_socket: Any | None = None

    def _blocked_socket(self, *args: Any, **kwargs: Any) -> Any:
        """Denies socket creation attempts."""
        raise SecurityError("Network access is disabled within the sandbox.")

    def __enter__(self) -> "NetworkGuard":
        """Activate the network barrier."""
        if not self.allow_network:
            self._real_socket = socket.socket
            setattr(socket, "socket", self._blocked_socket)
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc_val: BaseException | None,
                 exc_tb: TracebackType | None) -> None:
        """Restore original socket functionality."""
        if self._real_socket is not None:
            setattr(socket, "socket", self._real_socket)
            self._real_socket = None


def validate_code_security(code: str, authorized_imports: list[str]) -> None:
    """Validate python code string against import security policies."""
    tree = ast.parse(code)
    validator = ImportSecurityValidator(authorized_imports=authorized_imports)
    validator.visit(tree)


def create_safe_open(allowed_directories: list[str]) -> Callable[..., Any]:
    """Create a restricted version of open() limited to allowed directories."""
    def safe_open(file: str | Path, *args: Any, **kwargs: Any) -> Any:
        pass
    return safe_open
