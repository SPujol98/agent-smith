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

from mcp import Client, MCPError, StdioServerParameters
from mcp.types import CallToolResult, Tool

from agent_smith.sandbox.mcp_manual import build_manual

_T = TypeVar("_T")


class MCPToolError(Exception):
    """A tool reported an error; raised inside the sandboxed code."""


class MCPConnectionError(RuntimeError):
    """The connection to the MCP server could not be established."""


def _result_value(result: CallToolResult) -> Any:
    """Turn a raw MCP tool result into the value the code receives."""
    text = "\n".join(
        getattr(block, "text", f"[{block.type} content]")
        for block in result.content
    )
    if result.is_error:
        raise MCPToolError(text or "The tool reported an error")
    structured = result.structured_content
    if structured is None:
        return text
    if set(structured) == {"result"}:
        return structured["result"]
    return structured


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

    def sandbox_functions(self) -> dict[str, Callable[..., Any]]:
        """Every function the sandbox exposes: server tools + helpers."""
        helpers: dict[str, Callable[..., Any]] = {
            "list_resources": self.list_resources,
            "read_resource": self.read_resource,
            "list_prompts": self.list_prompts,
            "get_prompt": self.get_prompt,
        }
        tools = self.tool_functions()
        clash = tools.keys() & helpers.keys()
        if clash:
            raise MCPConnectionError(
                "Server tools use names reserved by the sandbox: "
                f"{', '.join(sorted(clash))}"
            )
        return {**helpers, **tools}

    def manual(self) -> str:
        """Manual of the server's tools, resources and prompts for the LLM."""
        try:
            resources = self.list_resources()
        except MCPError:
            resources = []
        try:
            prompts = self.list_prompts()
        except MCPError:
            prompts = []
        return build_manual(self.list_tools(), resources, prompts)

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

    def _collect(self, method: str, field: str) -> list[Any]:
        """All items of a paginated list request (list_resources...)."""
        items: list[Any] = []
        cursor: str | None = None
        while True:
            page = self._call(lambda c: getattr(c, method)(cursor=cursor))
            items.extend(getattr(page, field))
            cursor = page.next_cursor
            if not cursor:
                return items

    def list_tools(self) -> list[Tool]:
        """Return all the tools of the server, following pagination."""
        return self._collect("list_tools", "tools")

    def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        """Call a tool and return the raw MCP result."""
        return self._call(lambda c: c.call_tool(name, arguments))

    def _tool_function(self, tool: Tool) -> Callable[..., Any]:
        """Python function that calls `tool` on the server."""
        params = list(tool.input_schema.get("properties", {}))

        def call(*args: Any, **kwargs: Any) -> Any:
            if len(args) > len(params):
                raise TypeError(
                    f"{tool.name}() takes {len(params)} arguments "
                    f"but {len(args)} were given"
                )
            arguments = dict(zip(params, args))
            repeated = arguments.keys() & kwargs.keys()
            if repeated:
                raise TypeError(
                    f"{tool.name}() got multiple values for "
                    f"{', '.join(sorted(repeated))}"
                )
            arguments.update(kwargs)
            return _result_value(self.call_tool(tool.name, arguments))

        call.__name__ = tool.name
        call.__doc__ = tool.description
        return call

    def tool_functions(self) -> dict[str, Callable[..., Any]]:
        """One Python function per server tool, keyed by tool name."""
        return {
            tool.name: self._tool_function(tool) for tool in self.list_tools()
        }

    def list_resources(self) -> list[dict[str, str]]:
        """Resources (and resource templates) offered by the server."""
        resources = [
            {
                "uri": str(r.uri),
                "name": r.name,
                "description": r.description or "",
            }
            for r in self._collect("list_resources", "resources")
        ]
        templates = [
            {
                "uri": t.uri_template,
                "name": t.name,
                "description": t.description or "",
            }
            for t in self._collect(
                "list_resource_templates", "resource_templates"
            )
        ]
        return resources + templates

    def read_resource(self, uri: str) -> str:
        """Text content of a resource."""
        try:
            result = self._call(lambda c: c.read_resource(uri))
        except MCPError as exc:
            raise MCPToolError(str(exc)) from exc
        return "\n".join(
            getattr(item, "text", None)
            or f"[binary content: {item.mime_type}]"
            for item in result.contents
        )

    def list_prompts(self) -> list[dict[str, Any]]:
        """Prompts offered by the server, with their argument names."""
        return [
            {
                "name": p.name,
                "description": p.description or "",
                "arguments": [a.name for a in p.arguments or []],
            }
            for p in self._collect("list_prompts", "prompts")
        ]

    def get_prompt(self, name: str, **arguments: str) -> str:
        """Render a prompt as text ("role: message" per line)."""
        try:
            result = self._call(lambda c: c.get_prompt(name, arguments))
        except MCPError as exc:
            raise MCPToolError(str(exc)) from exc
        return "\n".join(
            f"{m.role}: "
            + getattr(m.content, "text", f"[{m.content.type} content]")
            for m in result.messages
        )
