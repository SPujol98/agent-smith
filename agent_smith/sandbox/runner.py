import io
import traceback
from agent_smith.sandbox.security import (
    FileSystemGuard,
    BuiltinsGuard,
    NetworkGuard,
    SecurityError,
    validate_code_security)
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.sandbox.timeout import TimeoutGuard
from agent_smith.config import SandboxConfig
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any


class SandboxRunner:
    def __init__(self, allowed_directories: Sequence[str | Path] | None = None,
                 authorized_imports: list[str] | None = None,
                 config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()
        self.allowed_directories = (
            allowed_directories if allowed_directories
            is not None else self.config.allowed_directories)
        self.authorized_imports = (
            authorized_imports if authorized_imports
            is not None else self.config.authorized_imports)

        self.fs_guard = FileSystemGuard(self.allowed_directories)
        self.builtins_guard = BuiltinsGuard(
            self.fs_guard,
            authorized_imports=self.authorized_imports
        )

    def run(self, code: str) -> ExecutionResult:
        validate_code_security(code, self.authorized_imports)
        execution_env: dict[str, Any] = {
            "__builtins__": self.builtins_guard.build_builtins()
            }

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        success = True
        error_msg: str | None = None
        with (redirect_stdout(stdout_buf), redirect_stderr(stderr_buf),
              NetworkGuard(), TimeoutGuard(
                  self.config.max_execution_time_seconds)):
            try:
                exec(code, execution_env)
            except TimeoutError as e:
                return ExecutionResult(
                    success=False,
                    stdout=stdout_buf.getvalue(),
                    stderr=stderr_buf.getvalue(),
                    result_env=execution_env,
                    error=str(e)
                )
            except (SecurityError, PermissionError):
                raise
            except Exception:
                success = False
                error_msg = traceback.format_exc()

        return ExecutionResult(
            success=success,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            result_env=execution_env,
            error=error_msg
        )
