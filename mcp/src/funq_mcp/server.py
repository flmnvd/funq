"""Typed MCP tools. Blocking Funq calls run off the MCP event loop."""

import json
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Literal

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from .errors import AdapterError
from .selectors import Selector


INSTRUCTIONS = (
    "Attach to an already running Funq-enabled Qt application using its explicit port. "
    "Inspect widgets and resolve selectors by path or exact object_name. GUI actions return dispatched, "
    "not verified: use funq_wait and inspect the resulting state. Actions are serialized per session. "
    "After a transport timeout the action outcome is unknown; attach again and inspect before retrying. "
    "Never automatically replay a mutating action. Failure responses include saved diagnostic artifacts. "
    "Use funq_trigger for actions opening modal dialogs; it is nonblocking. The adapter never launches or quits "
    "applications. funq_detach only closes the test connection. funq_set_properties is explicit fixture setup, "
    "while funq_type simulates keyboard input. Model read limits apply to MCP output; the current Qt plugin "
    "still traverses the entire model. Native OS dialogs and Qt Quick controls may need additional tooling."
)


def result(data, error=False, image=None):
    payload = {"ok": not error, "error" if error else "data": data}
    content = [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, allow_nan=False))]
    if image is not None:
        content.append(ImageContent(type="image", data=image, mimeType="image/png"))
    return CallToolResult(content=content, structuredContent=payload, isError=error)


def create_server(service):
    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {}
        finally:
            await anyio.to_thread.run_sync(service.close)

    server = FastMCP("Funq GUI testing", instructions=INSTRUCTIONS, lifespan=lifespan)
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    write = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
    session_change = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    async def invoke(function, *args, screenshot=False, **kwargs):
        try:
            data = await anyio.to_thread.run_sync(partial(function, *args, **kwargs))
            image = data.pop("image_base64") if screenshot else None
            return result(data, image=image)
        except AdapterError as error:
            return result(error.as_dict(), error=True)

    @server.tool(annotations=session_change, structured_output=False)
    async def funq_attach(port: int, host: str = "127.0.0.1", expected_class: str | None = None,
                          timeout: float = 10) -> CallToolResult:
        """Attach to an existing Funq listener. Require an explicit TCP port; optionally verify the main-window class."""
        return await invoke(service.attach, port, host, expected_class, timeout)

    @server.tool(annotations=read, structured_output=False)
    async def funq_sessions() -> CallToolResult:
        """List attached sessions and whether their TCP connections remain usable."""
        return await invoke(service.list_sessions)

    @server.tool(annotations=session_change, structured_output=False)
    async def funq_detach(session_id: str) -> CallToolResult:
        """Close a test connection and discard its session. The application keeps running."""
        return await invoke(service.detach, session_id)

    @server.tool(annotations=read, structured_output=False)
    async def funq_snapshot(session_id: str, selector: Selector | None = None, visible_only: bool = True,
                            offset: int = 0, limit: int = 100, save_artifact: bool = False) -> CallToolResult:
        """List compact widget records, including dialog classes. An optional selector scopes the query to its children.

        Paginate with next_offset. Full JSON is saved when requested or when output is truncated.
        """
        return await invoke(service.snapshot, session_id, selector, visible_only, offset, limit, save_artifact)

    @server.tool(annotations=read, structured_output=False)
    async def funq_find(session_id: str, selector: Selector, timeout: float = 10) -> CallToolResult:
        """Resolve exactly one object by full path or exact object_name. Ambiguous matches are returned as errors.

        This performs one lookup; use funq_wait when an object is expected to appear later.
        """
        return await invoke(service.find, session_id, selector, timeout)

    @server.tool(annotations=read, structured_output=False)
    async def funq_inspect(session_id: str, selector: Selector) -> CallToolResult:
        """Read an object's Qt properties. Large values are summarized and the complete properties saved as JSON."""
        return await invoke(service.inspect, session_id, selector)

    @server.tool(annotations=write, structured_output=False)
    async def funq_click(session_id: str, selector: Selector, button: Literal["left", "middle", "right"] = "left",
                         double: bool = False, timeout: float = 10) -> CallToolResult:
        """Click the center of a visible, enabled widget. For actions opening modal dialogs prefer funq_trigger."""
        return await invoke(service.click, session_id, selector, button, double, timeout)

    @server.tool(annotations=write, structured_output=False)
    async def funq_trigger(session_id: str, selector: Selector, timeout: float = 10) -> CallToolResult:
        """Schedule a visible, enabled QAction without blocking on a modal dialog. Wait for the resulting state."""
        return await invoke(service.trigger, session_id, selector, timeout)

    @server.tool(annotations=write, structured_output=False)
    async def funq_type(session_id: str, selector: Selector, text: str, replace: bool = False,
                        timeout: float = 10) -> CallToolResult:
        """Focus a widget and simulate text entry. replace uses Ctrl+A and Backspace; verify the resulting text."""
        return await invoke(service.type_text, session_id, selector, text, replace, timeout)

    @server.tool(annotations=write, structured_output=False)
    async def funq_shortcut(session_id: str, selector: Selector, keys: str, timeout: float = 10) -> CallToolResult:
        """Send a Qt key sequence such as Ctrl+O, Escape, or Return to a selected widget."""
        return await invoke(service.shortcut, session_id, selector, keys, timeout)

    @server.tool(annotations=write, structured_output=False)
    async def funq_set_properties(session_id: str, selector: Selector, properties: dict[str, Any]) -> CallToolResult:
        """Assign Qt properties for fixture setup and verify their values. This bypasses keyboard input handling."""
        return await invoke(service.set_properties, session_id, selector, properties)

    @server.tool(annotations=write, structured_output=False)
    async def funq_close_widget(session_id: str, selector: Selector) -> CallToolResult:
        """Schedule closing a selected widget. Wait for visibility=false or absence to verify closure."""
        return await invoke(service.close_widget, session_id, selector)

    @server.tool(annotations=read, structured_output=False)
    async def funq_wait(session_id: str, selector: Selector, properties: dict[str, Any] | None = None,
                        exists: bool = True, timeout: float = 10, interval: float = 0.2) -> CallToolResult:
        """Poll for existence, disappearance, or exact Qt property values with a bounded overall deadline.

        Missing objects are retried; ambiguity and connection errors stop immediately. timeout is at most 50 seconds.
        """
        return await invoke(service.wait, session_id, selector, properties, exists, timeout, interval)

    @server.tool(annotations=read, structured_output=False)
    async def funq_model_read(session_id: str, selector: Selector, offset: int = 0, limit: int = 100) -> CallToolResult:
        """Read cells from a tree/table/combo model, including parent itempath, row, column, and displayed value.

        The plugin dumps the full model before MCP output pagination; use on bounded test fixtures.
        """
        return await invoke(service.model_read, session_id, selector, offset, limit)

    @server.tool(annotations=write, structured_output=False)
    async def funq_model_select(session_id: str, selector: Selector, row: int, column: int = 0, itempath: str = "",
                                action: Literal["select", "edit", "click", "doubleclick"] = "select") -> CallToolResult:
        """Interact with a view cell. itempath identifies parent indexes using row-column pairs, e.g. 2-0/4-0."""
        return await invoke(service.model_select, session_id, selector, row, column, itempath, action)

    @server.tool(annotations=read, structured_output=False)
    async def funq_screenshot(session_id: str, selector: Selector | None = None) -> CallToolResult:
        """Return a PNG image and saved artifact path. Provide a widget selector, or omit it for the whole desktop."""
        return await invoke(service.screenshot, session_id, selector, screenshot=True)

    return server
