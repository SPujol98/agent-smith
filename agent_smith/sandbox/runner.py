from agent_smith.sandbox.security import (
    FileSystemGuard,
    BuiltinsGuard,
    NetworkGuard,
    validate_code_security)
from pathlib import Path
from typing import Any


class SandboxRunner:
    def __init__(self, allowed_directories: list[str | Path] | None = None,
                 authorized_imports: list[str] | None = None) -> None:
        self.allowed_directories = allowed_directories or []
        self.authorized_imports = authorized_imports or []
        self.fs_guard = FileSystemGuard(self.allowed_directories)
        self.builtins_guard = BuiltinsGuard(self.fs_guard)

    def run(self, code: str) -> dict[str, Any]:
        validate_code_security(code, self.authorized_imports)
        execution_env: dict[str, Any] = {
            "__builtins__": self.builtins_guard.build_builtins()
            }
        for module_name in self.authorized_imports:
            execution_env[module_name] = __import__(module_name)

        with NetworkGuard():
            exec(code, execution_env)
        return execution_env
