import ast
import builtins
import socket
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any

_real_open = builtins.open
_real_import = builtins.__import__


ALLOWED_DUNDERS: frozenset[str] = frozenset(
    {
        "__init__",
        "__len__",
        "__str__",
        "__repr__",
        "__eq__",
        "__iter__",
        "__next__",
        "__doc__",
        "__name__",
    }
)

FORBIDDEN_FRAME_ATTRS: frozenset[str] = frozenset(
    {
        "gi_frame",
        "gi_code",
        "f_back",
        "f_locals",
        "f_globals",
        "f_builtins",
        "f_code",
        "tb_frame",
        "cr_frame",
    }
)


_TYPES: frozenset[str] = frozenset(
    {
        "int",
        "float",
        "bool",
        "str",
        "list",
        "dict",
        "object",
        "type",
        "set",
        "tuple",
        "bytes",
        "bytearray",
        "complex",
        "frozenset",
        "slice",
    }
)

_OOP: frozenset[str] = frozenset(
    {
        "super",
        "property",
        "staticmethod",
        "classmethod",
    }
)

_FUNCTIONS: frozenset[str] = frozenset(
    {
        "len",
        "sorted",
        "map",
        "round",
        "chr",
        "ord",
        "sum",
        "print",
        "range",
        "min",
        "max",
        "abs",
        "all",
        "enumerate",
        "isinstance",
        "issubclass",
        "repr",
        "zip",
        "any",
        "filter",
        "reversed",
        "divmod",
        "pow",
        "bin",
        "hex",
        "oct",
        "hash",
        "id",
        "iter",
        "next",
        "callable",
        "format",
        "ascii",
        "hasattr",
        "dir",
    }
)

_CONSTANTS: frozenset[str] = frozenset({"Ellipsis", "NotImplemented"})

_INTERNALS: frozenset[str] = frozenset({"__build_class__"})


ALLOWED_BUILTINS: frozenset[str] = (
    _TYPES | _OOP | _FUNCTIONS | _CONSTANTS | _INTERNALS
)


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
        return is_module_allowed(module_name, self.authorized_imports)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if not self._is_module_allowed(alias.name):
                raise SecurityError(
                    "Unauthorized import detected: "
                    f"'{alias.name}' (line {node.lineno})"
                )
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
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in self.RESTRICTED_CALLS
        ):
            raise SecurityError(
                f"Forbidden call to '{node.func.id}()' "
                f"detected (line {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_FRAME_ATTRS:
            raise SecurityError(
                f"Access to frame inspection attribute '{node.attr}' "
                "is forbidden"
            )
        if (
            node.attr.startswith("__") and node.attr.endswith("__")
        ) and node.attr not in ALLOWED_DUNDERS:
            raise SecurityError(
                f"Access to restricted dunder attribute '{node.attr}' "
                "is forbidden"
            )
        self.generic_visit(node)


class FileSystemGuard:
    """Enforces directory boundary constraints and safe file operations."""

    def __init__(self, allowed_directories: Sequence[str | Path]) -> None:
        self.allowed_directories = self._normalize_paths(allowed_directories)

    def _normalize_paths(
        self, directories: Sequence[str | Path]
    ) -> list[Path]:
        """Convert input paths to canonical absolute Path instances."""
        return [Path(d).resolve() for d in directories]

    def validate_path(self, path: str | Path) -> Path:
        """Resolve and verify if a path falls strictly within
        allowed boundaries."""
        target = Path(path).resolve()
        for allowed_dir in self.allowed_directories:
            if target.is_relative_to(allowed_dir):
                return target
        raise SecurityError(
            f"Access denied: '{path}' (resolved to '{target}')"
            " is outside allowed directories."
        )

    def open(self, file: str | Path, *args: Any, **kwargs: Any) -> Any:
        """Safely open a file after validating its target directory."""
        target = self.validate_path(file)
        return _real_open(target, *args, **kwargs)


class BuiltinsGuard:
    """Constructs the sandbox builtins dictionary (allowlist approach)."""

    def __init__(
        self,
        file_system_guard: FileSystemGuard,
        authorized_imports: list[str] | None = None,
    ) -> None:
        self.fs_guard = file_system_guard
        self.authorized_imports = authorized_imports or []

    def _safe_import(
        self,
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        """Intercept runtime __import__ calls and validate against
        authorized imports."""
        if level > 0:
            raise SecurityError("Relative imports not allowed")
        if not is_module_allowed(name, self.authorized_imports):
            raise SecurityError(f"Import of module '{name}' is forbidden")
        return _real_import(name, globals, locals, fromlist, level)

    def build_builtins(self) -> dict[str, Any]:
        """Build the sandbox builtins from the allowlist.

        Starts from an empty dict and adds only ALLOWED_BUILTINS, every
        builtin exception class, and the guarded open and __import__.
        """
        safe_builtins: dict[str, Any] = {}
        for name in ALLOWED_BUILTINS:
            if hasattr(builtins, name):
                safe_builtins[name] = getattr(builtins, name)
        for name, obj in vars(builtins).items():
            if isinstance(obj, type) and issubclass(obj, BaseException):
                safe_builtins[name] = obj
        safe_builtins["open"] = self.fs_guard.open
        safe_builtins["__import__"] = self._safe_import
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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Restore original socket functionality."""
        if self._real_socket is not None:
            setattr(socket, "socket", self._real_socket)
            self._real_socket = None


def validate_code_security(code: str, authorized_imports: list[str]) -> None:
    """Validate python code string against import security policies."""
    tree = ast.parse(code)
    validator = ImportSecurityValidator(authorized_imports=authorized_imports)
    validator.visit(tree)


def is_module_allowed(module_name: str, authorized_imports: list[str]) -> bool:
    """Check if a module name matches the authorized imports allowlist."""
    for pattern in authorized_imports:
        if pattern == module_name:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if prefix == module_name or module_name.startswith(f"{prefix}."):
                return True
    return False
