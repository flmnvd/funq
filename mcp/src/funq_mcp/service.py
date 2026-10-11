"""Serialized GUI sessions, observable operations, and failure evidence."""

import base64
import json
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .client import create_client
from .errors import AdapterError


DEFAULT_PROPERTIES = ("objectName", "text", "windowTitle", "visible", "enabled", "checked", "checkState",
                      "value", "currentText", "currentIndex", "readOnly", "toolTip", "geometry")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def flatten_widgets(tree):
    stack = list(reversed(list(tree.values())))
    seen = set()
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if "classes" not in node:
            stack.extend(reversed(list(node.values())))
            continue
        path = node.get("path", "")
        if path not in seen:
            seen.add(path)
            yield node
        stack.extend(reversed(list((node.get("children") or {}).values())))


def compact(value, depth=0):
    if isinstance(value, str):
        return value if len(value) <= 1000 else value[:1000] + "... [truncated]"
    if depth >= 5:
        return "[nested value omitted]" if isinstance(value, (dict, list)) else value
    if isinstance(value, list):
        return [compact(item, depth + 1) for item in value[:30]]
    if isinstance(value, dict):
        return {key: compact(item, depth + 1) for key, item in list(value.items())[:50]}
    return value


def describe(obj):
    return {"path": obj.path, "classes": obj.classes}


@dataclass
class Session:
    id: str
    host: str
    port: int
    client: object
    commands: list
    lock: object = field(default_factory=threading.Lock)
    events: object = field(default_factory=lambda: deque(maxlen=1000))
    detached: bool = False


class FunqService:
    def __init__(self, funq_root, artifact_dir, client_factory=create_client, max_frame_bytes=32 * 1024 * 1024):
        self.funq_root = Path(funq_root)
        self.artifact_dir = Path(artifact_dir).resolve()
        self.client_factory = client_factory
        self.max_frame_bytes = max_frame_bytes
        self.sessions = {}
        self.pending = set()
        self.lock = threading.Lock()

    @staticmethod
    def _timeout(timeout):
        if not 0 < timeout <= 50:
            raise AdapterError("InvalidTimeout", "timeout must be greater than 0 and at most 50 seconds")
        return timeout

    def _json_artifact(self, session, name, data):
        directory = self.artifact_dir / session.id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (name + "-" + uuid.uuid4().hex + ".json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        return str(path)

    def _png_artifact(self, session, data):
        raw = base64.b64decode(data, validate=True)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AdapterError("InvalidScreenshot", "Funq did not return a PNG image")
        directory = self.artifact_dir / session.id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / ("screenshot-" + uuid.uuid4().hex + ".png")
        path.write_bytes(raw)
        return str(path)

    def _diagnostics(self, session):
        artifacts = {}
        try:
            artifacts["events"] = self._json_artifact(session, "events", list(session.events))
        except OSError as error:
            artifacts["save_error"] = str(error)
        # Only use time still remaining in the failed operation's budget.
        client = session.client
        if client.connected and client.deadline and client.deadline - time.monotonic() > 0.1:
            client.deadline = min(client.deadline, time.monotonic() + 2)
            try:
                tree = client.widgets_list(with_properties=True)
                artifacts["widgets"] = self._json_artifact(session, "widgets", tree)
                image = client.send_command("grab", format="PNG")
                artifacts["screenshot"] = self._png_artifact(session, image["data"])
            except Exception as error:
                artifacts["capture_error"] = str(error)
        return artifacts

    def _get(self, session_id):
        with self.lock:
            session = self.sessions.get(session_id)
        if session is None:
            raise AdapterError("UnknownSession", "Use funq_attach to create a session.", session_id=session_id)
        return session

    def _run(self, session_id, operation, callback, timeout=10, selector=None):
        timeout = self._timeout(timeout)
        session = self._get(session_id)
        start = time.monotonic()
        if not session.lock.acquire(timeout=timeout):
            raise AdapterError("SessionBusy", "Another GUI operation is still running; no command was sent.")
        try:
            if session.detached or not session.client.connected:
                raise AdapterError("SessionDisconnected", "Attach again before issuing more GUI operations.")
            session.client.deadline = start + timeout
            event = {"time": utc_now(), "operation": operation}
            if selector is not None:
                event["selector"] = selector.model_dump(exclude_none=True)
            session.events.append(event)
            try:
                result = callback(session)
            except Exception as error:
                if not isinstance(error, AdapterError):
                    error = AdapterError(getattr(error, "classname", "OperationFailed"),
                                         getattr(error, "desc", str(error)))
                event.update(error=error.as_dict(), elapsed_seconds=round(time.monotonic() - start, 3))
                error.details["artifacts"] = self._diagnostics(session)
                if not session.client.connected:
                    error.details["reattach_required"] = True
                raise error
            event.update(status="completed", elapsed_seconds=round(time.monotonic() - start, 3))
            return result
        finally:
            session.client.deadline = None
            session.lock.release()

    def attach(self, port, host="127.0.0.1", expected_class=None, timeout=10):
        self._timeout(timeout)
        if not 1 <= port <= 65535:
            raise AdapterError("InvalidPort", "port must be between 1 and 65535")
        if not host or not host.strip():
            raise AdapterError("InvalidHost", "host must be non-empty")
        # Resolve the peer through the connection so host aliases cannot create
        # competing sessions. Do not hold the registry lock during network I/O.
        client, reserved = None, None
        try:
            deadline = time.monotonic() + timeout
            client = self.client_factory(self.funq_root, host, port, timeout, self.max_frame_bytes)
            with self.lock:
                for existing in self.sessions.values():
                    if existing.client.endpoint == client.endpoint and existing.client.connected:
                        raise AdapterError("AlreadyAttached", "Use the existing session.", session_id=existing.id)
                if client.endpoint in self.pending:
                    raise AdapterError("SessionBusy", "Attachment to this application is already in progress")
                if len(self.sessions) + len(self.pending) >= 16:
                    raise AdapterError("SessionLimit", "Detach an existing session before attaching another application")
                self.pending.add(client.endpoint)
                reserved = client.endpoint
            client.deadline = deadline
            commands = sorted({name.split("(", 1)[0] for name in client._list_commands()["commands"]})
            client.commands = set(commands)
            required = {"object_find", "widgets_list", "object_properties"}
            if not required.issubset(commands):
                raise AdapterError("IncompatibleServer", "Required Funq commands are missing.",
                                   missing=sorted(required - set(commands)))
            windows = client.widgets_list(with_properties=True, recursive=False)
            if expected_class and not any(expected_class in node.get("classes", [])
                                          for node in flatten_widgets(windows)):
                raise AdapterError("UnexpectedApplication", "The expected main-window class was not found.",
                                   expected_class=expected_class)
            sid = uuid.uuid4().hex
            session = Session(sid, host, port, client, commands)
            with self.lock:
                self.sessions[sid] = session
            client.deadline = None
            nodes = list(flatten_widgets(windows))
            return {"session_id": sid, "host": host, "port": port, "commands": commands,
                    "windows": [self._node(node) for node in nodes[:30]], "window_count": len(nodes)}
        except Exception as error:
            if client is not None:
                client.close()
            if isinstance(error, AdapterError):
                raise
            raise AdapterError(getattr(error, "classname", "AttachFailed"), str(error)) from error
        finally:
            if reserved is not None:
                with self.lock:
                    self.pending.discard(reserved)

    def list_sessions(self):
        with self.lock:
            return [{"session_id": s.id, "host": s.host, "port": s.port, "connected": s.client.connected}
                    for s in self.sessions.values()]

    def detach(self, session_id):
        session = self._get(session_id)
        if not session.lock.acquire(timeout=5):
            raise AdapterError("SessionBusy", "A GUI operation is running; retry detach when it has finished.")
        try:
            session.detached = True
            session.client.close()
            with self.lock:
                self.sessions.pop(session_id, None)
            return {"session_id": session_id, "detached": True}
        finally:
            session.lock.release()

    def close(self):
        with self.lock:
            for session in self.sessions.values():
                session.client.close()
            self.sessions.clear()

    @staticmethod
    def _object(session, selector):
        # object() uses object_find for both paths and properties, preserving
        # Funq's AmbiguousObjectMatch errors instead of picking a first match.
        return session.client.object(timeout=0, **selector.command())

    @staticmethod
    def _node(node):
        props = node.get("properties") or {}
        selected = {name: props[name] for name in DEFAULT_PROPERTIES if name in props}
        return {"path": node.get("path", ""), "classes": node.get("classes", []),
                "properties": compact(selected), "properties_truncated": compact(selected) != selected,
                "child_count": len(node.get("children") or {})}

    def snapshot(self, session_id, selector=None, visible_only=True, offset=0, limit=100, save_artifact=False):
        def work(session):
            if offset < 0 or not 1 <= limit <= 500:
                raise AdapterError("InvalidPage", "offset must be non-negative and limit between 1 and 500")
            fields = {"with_properties": True, "recursive": True}
            if selector:
                fields["oid"] = self._object(session, selector).oid
            tree = session.client.send_command("widgets_list", **fields)
            nodes = [self._node(n) for n in flatten_widgets(tree)
                     if not visible_only or (n.get("properties") or {}).get("visible") is True]
            page, size = [], 0
            for node in nodes[offset:offset + limit]:
                length = len(json.dumps(node, ensure_ascii=False))
                if page and size + length > 32000:
                    break
                page.append(node)
                size += length
            more = offset + len(page) < len(nodes)
            result = {"widgets": page, "total": len(nodes), "offset": offset,
                      "next_offset": offset + len(page) if more else None}
            if save_artifact or more or any(n["properties_truncated"] for n in page):
                result["artifact"] = self._json_artifact(session, "widgets", tree)
            return result
        return self._run(session_id, "snapshot", work, selector=selector)

    def find(self, session_id, selector, timeout=10):
        return self._run(session_id, "find", lambda s: describe(self._object(s, selector)), timeout, selector)

    def inspect(self, session_id, selector):
        def work(session):
            obj = self._object(session, selector)
            props = obj.properties()
            result = {**describe(obj), "properties": compact(props), "properties_truncated": compact(props) != props}
            if result["properties_truncated"]:
                result["artifact"] = self._json_artifact(session, "properties", props)
            return result
        return self._run(session_id, "inspect", work, selector=selector)

    def _mutate(self, session_id, selector, operation, callback, timeout=10):
        def work(session):
            obj = self._object(session, selector)
            props = obj.properties()
            if props.get("enabled") is False or props.get("visible") is False:
                raise AdapterError("TargetInactive", "The target must be visible and enabled.", target=describe(obj))
            callback(session.client, obj)
            return {**describe(obj), "status": "dispatched", "verification_required": True}
        return self._run(session_id, operation, work, timeout, selector)

    def click(self, session_id, selector, button="left", double=False, timeout=10):
        if button not in ("left", "middle", "right") or (double and button != "left"):
            raise AdapterError("InvalidClick", "Double click supports the left button only")
        action = "doubleclick" if double else {"left": "click", "middle": "middleclick", "right": "rightclick"}[button]
        return self._mutate(session_id, selector, "click",
                            lambda c, o: c.send_command("widget_click", oid=o.oid, mouseAction=action), timeout)

    def trigger(self, session_id, selector, timeout=10):
        return self._mutate(session_id, selector, "trigger",
                            lambda c, o: c.send_command("action_trigger", oid=o.oid, blocking=False), timeout)

    def type_text(self, session_id, selector, text, replace=False, timeout=10):
        if len(text) > 10000:
            raise AdapterError("TextTooLong", "Text input is limited to 10000 characters per operation")
        def work(client, obj):
            client.send_command("widget_activate_focus", oid=obj.oid)
            if replace:
                client.send_command("shortcut", oid=obj.oid, keysequence="Ctrl+A")
                client.send_command("shortcut", oid=obj.oid, keysequence="Backspace")
            client.send_command("widget_keyclick", oid=obj.oid, text=text)
        return self._mutate(session_id, selector, "type", work, timeout)

    def shortcut(self, session_id, selector, keys, timeout=10):
        if not keys or len(keys) > 200:
            raise AdapterError("InvalidShortcut", "Provide a non-empty Qt key sequence, at most 200 characters")
        return self._mutate(session_id, selector, "shortcut",
                            lambda c, o: c.send_command("shortcut", oid=o.oid, keysequence=keys), timeout)

    def set_properties(self, session_id, selector, properties):
        if not properties:
            raise AdapterError("InvalidProperties", "Provide at least one property")
        def work(session):
            obj = self._object(session, selector)
            obj.set_properties(**properties)
            actual = obj.properties()
            mismatches = {key: actual.get(key) for key, value in properties.items()
                          if key not in actual or actual[key] != value}
            if mismatches:
                raise AdapterError("PropertyVerificationFailed", "Some properties did not retain the requested values.",
                                   actual=compact(mismatches))
            return {**describe(obj), "properties": compact(properties), "verified": True}
        return self._run(session_id, "set_properties", work, selector=selector)

    def close_widget(self, session_id, selector):
        return self._mutate(session_id, selector, "close_widget", lambda c, o: c.send_command("widget_close", oid=o.oid))

    def wait(self, session_id, selector, properties=None, exists=True, timeout=10, interval=0.2):
        if not 0.05 <= interval <= 2:
            raise AdapterError("InvalidInterval", "interval must be between 0.05 and 2 seconds")
        if not exists and properties:
            raise AdapterError("InvalidCondition", "Property conditions require exists=true")
        def work(session):
            last = None
            while time.monotonic() < session.client.deadline:
                try:
                    obj = self._object(session, selector)
                    last = obj.properties() if properties else {}
                    if exists and all(key in last and last[key] == val for key, val in (properties or {}).items()):
                        return {**describe(obj), "matched": True, "properties": compact(last)}
                except Exception as error:
                    if getattr(error, "classname", None) not in ("ObjectNotFound", "NotRegisteredObject"):
                        raise
                    last = None
                    if not exists:
                        return {"matched": True, "exists": False}
                remaining = session.client.deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(interval, remaining))
            raise AdapterError("ConditionTimeout", "The GUI did not reach the requested state.", last_properties=compact(last))
        return self._run(session_id, "wait", work, timeout, selector)

    def model_read(self, session_id, selector, offset=0, limit=100):
        def work(session):
            if offset < 0 or not 1 <= limit <= 500:
                raise AdapterError("InvalidPage", "offset must be non-negative and limit between 1 and 500")
            view = self._object(session, selector)
            model = session.client.send_command("model", oid=view.oid)
            data = session.client.send_command("model_items", oid=model["oid"])
            stack = list(reversed(data.get("items", [])))
            items = []
            while stack:
                item = stack.pop()
                items.append({key: item[key] for key in ("itempath", "row", "column", "value", "check_state") if key in item})
                stack.extend(reversed(item.get("items", [])))
            page, size = [], 0
            for item in items[offset:offset + limit]:
                entry = compact(item)
                length = len(json.dumps(entry, ensure_ascii=False))
                if page and size + length > 32000:
                    break
                page.append(entry)
                size += length
            more = offset + len(page) < len(items)
            result = {**describe(view), "items": page, "total": len(items), "offset": offset,
                      "next_offset": offset + len(page) if more else None, "server_pagination": False}
            if more or page != items[offset:offset + len(page)]:
                result["artifact"] = self._json_artifact(session, "model", items)
            return result
        return self._run(session_id, "model_read", work, selector=selector)

    def model_select(self, session_id, selector, row, column=0, itempath="", action="select"):
        if not 0 <= row <= 2147483647 or not 0 <= column <= 2147483647 or action not in ("select", "edit", "click", "doubleclick"):
            raise AdapterError("InvalidModelAction", "Use non-negative 32-bit row/column and a supported action")
        if itempath and (not re.fullmatch(r"[0-9]+-[0-9]+(?:/[0-9]+-[0-9]+)*", itempath)
                         or any(int(part) > 2147483647 for part in re.split(r"[-/]", itempath))):
            raise AdapterError("InvalidItemPath", "itempath must contain parent row-column pairs, such as 2-0/4-0")
        return self._mutate(session_id, selector, "model_select",
                            lambda c, o: c.send_command("model_item_action", oid=o.oid, row=row, column=column,
                                                       itempath=itempath, itemaction=action, origin="center",
                                                       offset_x=0, offset_y=0))

    def screenshot(self, session_id, selector=None):
        def work(session):
            fields = {"format": "PNG"}
            if selector:
                fields["oid"] = self._object(session, selector).oid
            data = session.client.send_command("grab", **fields)
            path = self._png_artifact(session, data["data"])
            return {"path": path, "mime_type": "image/png", "image_base64": data["data"]}
        return self._run(session_id, "screenshot", work, selector=selector)
