"""Synchronous facade over the asynchronous MCP client.

The MCP SDK is async, while the sandbox runner is synchronous. MCPClient
keeps the connection open in a background thread that runs its own event
loop; synchronous code sends requests to that loop and waits for them.
"""

import asyncio
import shlex
import threading
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, TypeVar

from mcp import Client, StdioServerParameters
from mcp.types import CallToolResult, Tool

_T = TypeVar("_T")


class MCPConnectionError(RuntimeError):
    """The connection to the MCP server could not be established."""


class MCPClient:
    """Synchronous MCP client, used as a context manager."""

    def __init__(self, target: Any, timeout: float = 600.0) -> None:
        self._target = target
        self._timeout = timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._client: Client | None = None
        self._error: BaseException | None = None

    @classmethod
    def from_stdio(
        cls, command: str, env: dict[str, str] | None = None
    ) -> "MCPClient":
        """Launch `command` as the server and talk to it over stdin/stdout."""
        parts = shlex.split(command)
        if not parts:
            raise ValueError("Empty MCP server command")
        params = StdioServerParameters(
            command=parts[0], args=parts[1:], env=env
        )
        return cls(params)

    @classmethod
    def from_url(cls, url: str) -> "MCPClient":
        """Connect to a server over streamable HTTP."""
        return cls(url)

    def __enter__(self) -> "MCPClient":
        """Start the background thread and wait until the server
        is connected."""
        self._thread.start()
        if not self._ready.wait(self._timeout):
            raise MCPConnectionError("Timed out connecting to MCP server")
        if self._error is not None:
            raise MCPConnectionError(
                f"Could not connect to MCP server: {self._error}"
            ) from self._error
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection and stop the background thread."""
        if self._stop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(self._timeout)

    def _run_loop(self) -> None:
        """Body of the background thread: run the session in its own loop."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session())
        finally:
            self._loop.close()

    async def _session(self) -> None:
        """Keep the connection open until __exit__ sets the stop event."""
        self._stop = asyncio.Event()
        try:
            async with Client(self._target) as client:
                self._client = client
                self._ready.set()
                await self._stop.wait()
        except Exception as exc:
            while inner := getattr(exc, "exceptions", None):
                exc = inner[0]
            self._error = exc
        finally:
            self._client = None
            self._ready.set()

    def _call(self, request: Callable[[Client], Awaitable[_T]]) -> _T:
        """Run `request(client)` in the client's loop and wait for
        the result."""
        if self._client is None:
            raise MCPConnectionError("MCP client is not connected")
        client = self._client

        async def runner() -> _T:
            return await request(client)

        future = asyncio.run_coroutine_threadsafe(runner(), self._loop)
        return future.result(self._timeout)

    def list_tools(self) -> list[Tool]:
        """Return all the tools of the server, following pagination."""
        tools: list[Tool] = []
        cursor: str | None = None
        while True:
            page = self._call(lambda c: c.list_tools(cursor=cursor))
            tools.extend(page.tools)
            cursor = page.next_cursor
            if not cursor:
                return tools

    def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        """Call a tool and return the raw MCP result."""
        return self._call(lambda c: c.call_tool(name, arguments))
