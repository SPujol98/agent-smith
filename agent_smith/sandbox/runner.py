import io
import multiprocessing
import pickle
import time
import traceback
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, TextIO, cast

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


class _PipeWriter(io.TextIOBase):
    """File-like object that sends every write to the parent process."""

    def __init__(self, conn: Connection, channel: str) -> None:
        super().__init__()
        self._conn = conn
        self._channel = channel

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if text:
            self._conn.send((self._channel, text))
        return len(text)


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
        deadline = time.monotonic() + timeout if timeout > 0 else None
        stdout: list[str] = []
        stderr: list[str] = []
        try:
            while True:
                remaining = (
                    None
                    if deadline is None
                    else max(0.0, deadline - time.monotonic())
                )
                if not parent_conn.poll(remaining):
                    return ExecutionResult(
                        success=False,
                        stdout="".join(stdout),
                        stderr="".join(stderr),
                        result_env={},
                        error=(
                            "TimeoutError: Execution timed out after "
                            f"{timeout} seconds (output may be partial)"
                        ),
                    )
                message = parent_conn.recv()
                if message[0] == "stdout":
                    stdout.append(message[1])
                elif message[0] == "stderr":
                    stderr.append(message[1])
                elif message[0] == "raise":
                    raise message[1]
                else:
                    _, success, env, error = message
                    return ExecutionResult(
                        success=success,
                        stdout="".join(stdout),
                        stderr="".join(stderr),
                        result_env=env,
                        error=error,
                    )
        finally:
            if process.is_alive():
                process.kill()
            process.join()
            parent_conn.close()

    def _child_main(self, conn: Connection, code: str) -> None:
        execution_env: dict[str, Any] = {
            "__builtins__": self.builtins_guard.build_builtins(),
            "__name__": "__main__",
        }
        try:
            with (
                redirect_stdout(cast(TextIO, _PipeWriter(conn, "stdout"))),
                redirect_stderr(cast(TextIO, _PipeWriter(conn, "stderr"))),
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
                        _picklable_items(execution_env),
                        traceback.format_exc(),
                    )
                else:
                    message = (
                        "done",
                        True,
                        _picklable_items(execution_env),
                        None,
                    )
            conn.send(message)
        finally:
            conn.close()
