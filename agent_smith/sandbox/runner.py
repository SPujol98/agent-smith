import io
import multiprocessing
import pickle
import traceback
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from agent_smith.config import SandboxConfig
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.sandbox.security import (
    BuiltinsGuard,
    FileSystemGuard,
    NetworkGuard,
    SecurityError,
    validate_code_security,
)

_MP_CONTEXT = multiprocessing.get_context("fork")


class SandboxRunner:
    def __init__(
        self,
        allowed_directories: Sequence[str | Path] | None = None,
        authorized_imports: list[str] | None = None,
        config: SandboxConfig | None = None,
    ) -> None:
        self.config = config or SandboxConfig()
        self.allowed_directories = (
            allowed_directories
            if allowed_directories is not None
            else self.config.allowed_directories
        )
        self.authorized_imports = (
            authorized_imports
            if authorized_imports is not None
            else self.config.authorized_imports
        )

        self.fs_guard = FileSystemGuard(self.allowed_directories)
        self.builtins_guard = BuiltinsGuard(
            self.fs_guard, authorized_imports=self.authorized_imports
        )

    def run(self, code: str) -> ExecutionResult:
        try:
            validate_code_security(code, self.authorized_imports)
        except (SyntaxError, ValueError) as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                result_env={},
                error="".join(traceback.format_exception_only(type(e), e)),
            )

        parent_conn, child_conn = _MP_CONTEXT.Pipe()
        process = _MP_CONTEXT.Process(
            target=self._child_main, args=(child_conn, code), daemon=True
        )
        process.start()
        child_conn.close()
        timeout = self.config.max_execution_time_seconds
        try:
            if not parent_conn.poll(timeout if timeout > 0 else None):
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr="",
                    result_env={},
                    error=("TimeoutError: Execution timed out after "
                           f"{timeout} seconds"),
                )
            message = parent_conn.recv()
        finally:
            if process.is_alive():
                process.kill()
            process.join()
            parent_conn.close()
        if message[0] == "raise":
            raise message[1]
        return ExecutionResult(
            success=message[1],
            stdout=message[2],
            stderr=message[3],
            result_env=message[4],
            error=message[5],
        )

    def _child_main(self, conn: Connection, code: str) -> None:
        execution_env: dict[str, Any] = {
            "__builtins__": self.builtins_guard.build_builtins(),
            "__name__": "__main__",
        }
        try:
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            with (
                redirect_stdout(stdout_buf),
                redirect_stderr(stderr_buf),
                NetworkGuard(),
            ):
                message: tuple[Any, ...]
                try:
                    exec(code, execution_env)
                except (SecurityError, PermissionError) as e:
                    message = ("raise", e)
                except Exception:
                    message = (
                        "done",
                        False,
                        stdout_buf.getvalue(),
                        stderr_buf.getvalue(),
                        _picklable_items(execution_env),
                        traceback.format_exc(),
                    )
                else:
                    message = (
                        "done",
                        True,
                        stdout_buf.getvalue(),
                        stderr_buf.getvalue(),
                        _picklable_items(execution_env),
                        None,
                    )
            conn.send(message)
        finally:
            conn.close()


def _picklable_items(execution_env: dict[str, Any]) -> dict[str, Any]:
    """Return the namespace values that can be sent to the parent process
    (modules and functions defined by the code are dropped)"""
    pick_items: dict[str, Any] = {}
    for name, obj in execution_env.items():
        if name == "__builtins__":
            continue
        try:
            pickle.dumps(obj)
            pick_items[name] = obj
        except Exception:
            continue
    return pick_items
