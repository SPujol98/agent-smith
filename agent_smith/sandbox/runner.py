import io
import multiprocessing
import os
import pickle
import resource
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from multiprocessing.connection import Connection
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO, cast

from agent_smith.config import SandboxConfig
from agent_smith.sandbox.mcp_client import MCPClient, MCPConnectionError
from agent_smith.sandbox.result import ExecutionResult
from agent_smith.sandbox.security import (
    BuiltinsGuard,
    FileSystemGuard,
    NetworkGuard,
    SecurityError,
    validate_code_security,
)

_MP_CONTEXT = multiprocessing.get_context("fork")
_MB = 1024 * 1024
_FINAL_ANSWER_MANUAL = (
    "Always available:\n"
    "- final_answer(answer: str) -> None: Give the final answer and stop "
    "the execution."
)


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


class _FinalAnswer(BaseException):
    """Raised by final_answer() to stop the execution.

    Inherits from BaseException so `except Exception` in the user's code
    cannot swallow it.
    """


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


def _current_address_space() -> int:
    """Virtual memory already mapped by this process, in bytes (Linux)."""
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            pages = int(statm.read().split()[0])
    except (OSError, ValueError, IndexError):
        return 0
    return pages * os.sysconf("SC_PAGE_SIZE")


def _apply_memory_limit(max_memory_mb: int) -> None:
    """Let the code allocate at most max_memory_mb on top of what the forked
    child already uses."""
    if max_memory_mb <= 0:
        return
    limit = _current_address_space() + max_memory_mb * _MB
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, hard))


def _make_proxy(conn: Connection, name: str) -> Callable[..., Any]:
    """Function for the child that runs the tool `name` in the parent."""

    def proxy(*args: Any, **kwargs: Any) -> Any:
        message = (
            "call",
            name,
            args,
            kwargs,
        )
        conn.send(message)
        status, payload = conn.recv()
        if status == "error":
            raise payload
        return payload

    proxy.__name__ = name
    return proxy


def _transferable_exception(exc: BaseException) -> BaseException:
    """Return exc if it can be sent through the pipe, or an equivalent."""
    try:
        pickle.dumps(exc)
    except Exception:
        return RuntimeError(f"{type(exc).__name__}: {exc}")
    return exc


class SandboxRunner:
    def __init__(
        self,
        allowed_directories: Sequence[str | Path] | None = None,
        authorized_imports: list[str] | None = None,
        config: SandboxConfig | None = None,
        functions: Mapping[str, Callable[..., Any]] | None = None,
        mcp_stdio: str | None = None,
        mcp_url: str | None = None,
        mcp_env: dict[str, str] | None = None,
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
        self.functions = dict(functions or {})
        if "final_answer" in self.functions:
            raise ValueError("'final_answer' is reserved by the sandbox.")

        if mcp_stdio and mcp_url:
            raise ValueError("Use either mcp_stdio or mcp_url, not both")
        self._mcp: MCPClient | None = None
        if mcp_stdio:
            self._mcp = MCPClient.from_stdio(mcp_stdio, env=mcp_env)
        elif mcp_url:
            self._mcp = MCPClient.from_url(mcp_url)
        self.manual = _FINAL_ANSWER_MANUAL
        self.fs_guard = FileSystemGuard(self.allowed_directories)
        self.builtins_guard = BuiltinsGuard(
            self.fs_guard, authorized_imports=self.authorized_imports
        )

    def __enter__(self) -> "SandboxRunner":
        """Connect to the MCP server (if any) and expose its functions."""
        if self._mcp is None:
            return self
        self._mcp.__enter__()
        try:
            mcp_functions = self._mcp.sandbox_functions()
            clash = mcp_functions.keys() & (self.functions.keys()
                                            | {"final_answer"})
            if clash:
                raise MCPConnectionError(
                    "MCP server uses names already taken in the sandbox: "
                    f"{', '.join(sorted(clash))}"
                )
            self.functions.update(mcp_functions)
            self.manual = f"{_FINAL_ANSWER_MANUAL}\n\n{self._mcp.manual()}"
        except BaseException:
            self._mcp.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        """Close the MCP connection (if any)."""
        if self._mcp is not None:
            self._mcp.__exit__(exc_type, exc, tb)

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
        except SecurityError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                result_env={},
                error=f"SecurityError: {e}",
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
                try:
                    message = parent_conn.recv()
                except EOFError:
                    process.join()
                    return ExecutionResult(
                        success=False,
                        stdout="".join(stdout),
                        stderr="".join(stderr),
                        result_env={},
                        error=(
                            "SandboxError: execution process terminated "
                            f"unexpectedly (exit code {process.exitcode})"
                        ),
                    )
                if message[0] == "stdout":
                    stdout.append(message[1])
                elif message[0] == "stderr":
                    stderr.append(message[1])
                elif message[0] == "raise":
                    raise message[1]
                elif message[0] == "call":
                    started = time.monotonic()
                    parent_conn.send(self._call_function(*message[1:]))
                    if deadline is not None:
                        deadline += time.monotonic() - started
                else:
                    _, success, env, error, final_value = message
                    return ExecutionResult(
                        success=success,
                        stdout="".join(stdout),
                        stderr="".join(stderr),
                        result_env=env,
                        error=error,
                        is_finished=final_value is not None,
                        final_answer_value=final_value,
                    )
        finally:
            if process.is_alive():
                process.kill()
            process.join()
            parent_conn.close()

    def _call_function(
        self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[str, Any]:
        """Run a tool for the child and build the reply message."""
        try:
            value = self.functions[name](*args, **kwargs)
            pickle.dumps(value)
        except Exception as exc:
            return ("error", _transferable_exception(exc))
        return ("ok", value)

    def _child_main(self, conn: Connection, code: str) -> None:
        _apply_memory_limit(self.config.max_memory_mb)
        answers: list[str] = []

        def final_answer(answer: Any) -> None:
            answers.append(str(answer))
            raise _FinalAnswer

        execution_env: dict[str, Any] = {
            "__builtins__": self.builtins_guard.build_builtins(),
            "__name__": "__main__",
            "final_answer": final_answer,
        }
        for name in self.functions:
            execution_env[name] = _make_proxy(conn, name)
        try:
            with (
                redirect_stdout(cast(TextIO, _PipeWriter(conn, "stdout"))),
                redirect_stderr(cast(TextIO, _PipeWriter(conn, "stderr"))),
                NetworkGuard(),
            ):
                message: tuple[Any, ...]
                try:
                    exec(code, execution_env)
                except _FinalAnswer:
                    message = (
                        "done",
                        True,
                        _picklable_items(execution_env),
                        None,
                    )
                except (KeyboardInterrupt, SystemExit) as e:
                    message = ("raise", e)
                except MemoryError:
                    message = (
                        "done",
                        False,
                        {},
                        "MemoryError: memory limit"
                        f" of {self.config.max_memory_mb} MB exceeded",
                    )
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
            if message[0] == "done":
                message += (answers[0] if answers else None,)
            conn.send(message)
        finally:
            conn.close()
