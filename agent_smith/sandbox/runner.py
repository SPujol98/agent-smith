from agent_smith.sandbox.security import (
    FileSystemGuard,
    BuiltinsGuard)
from pathlib import Path


class SandboxRunner:
    def __init__(self, allowed_directories: list[str | Path] | None = None,
                 authorized_imports: list[str] | None = None) -> None:
        self.allowed_directories = allowed_directories or []
        self.authorized_imports = authorized_imports or []
        self.fs_guard = FileSystemGuard(self.allowed_directories)
        self.builtins_guard = BuiltinsGuard(self.fs_guard)


    def run(self, code: str) -> None:
        ...
