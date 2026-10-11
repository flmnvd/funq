import base64
import copy
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path

import pytest

from funq_mcp.service import FunqService

sys.dont_write_bytecode = True

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP9sAAAAASUVORK5CYII="
)
COMMANDS = ("list_commands", "widgets_list", "object_find", "object_properties", "object_set_properties",
            "action_trigger", "widget_click", "widget_keyclick", "widget_activate_focus", "shortcut",
            "widget_close", "model", "model_items", "model_item_action", "grab")


class FakeFunq:
    """Speak Funq framing over a real TCP socket, including fragmented replies."""

    def __init__(self):
        self.requests = []
        self.overrides = {}
        self.objects = {
            "main": self.obj(42, "main", ["CMainWindow", "QWidget", "QObject"]),
            "settings": self.obj(43, "Tools::s_pSettings", ["QAction", "QObject"]),
            "apply": self.obj(44, "apply", ["QPushButton", "QWidget", "QObject"]),
            "edit": self.obj(45, "edit", ["QLineEdit", "QWidget", "QObject"], text="original"),
            "tree": self.obj(46, "tree", ["QTreeView", "QAbstractItemView", "QWidget", "QObject"]),
        }
        self.guard = threading.Lock()
        self.fragment = False
        self.fragment_delay = 0
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                while True:
                    try:
                        header = self.rfile.readline()
                    except OSError:
                        return
                    if not header:
                        return
                    data = self.rfile.read(int(header))
                    if not data:
                        return
                    request = json.loads(data)
                    with outer.guard:
                        outer.requests.append(request)
                    response = outer.respond(request)
                    if response is None:
                        return
                    if isinstance(response, bytes):
                        frame = response
                    else:
                        body = json.dumps(response, ensure_ascii=False).encode("utf-8")
                        frame = str(len(body)).encode() + b"\n" + body
                    try:
                        if outer.fragment:
                            for i in range(0, len(frame), 3):
                                self.request.sendall(frame[i:i + 3])
                                if outer.fragment_delay:
                                    time.sleep(outer.fragment_delay)
                        else:
                            self.request.sendall(frame)
                    except OSError:
                        return

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    @staticmethod
    def obj(oid, name, classes, **props):
        return {"oid": oid, "path": "main/" + name, "classes": classes,
                "properties": {"objectName": name, "visible": True, "enabled": True, **props}}

    @staticmethod
    def failure(name, description="test failure"):
        return {"success": False, "errName": name, "errDesc": description}

    def respond(self, req):
        action = req["action"]
        if action in self.overrides:
            return self.overrides[action](req)
        objects = list(self.objects.values())
        if action == "list_commands":
            return {"commands": [name + "(QtJson::JsonObject)" for name in COMMANDS]}
        if action == "widgets_list":
            nodes = {o["path"]: {k: copy.deepcopy(v) for k, v in o.items() if k != "oid"}
                     for o in objects if "QWidget" in o["classes"]}
            return nodes
        if action == "object_find":
            matches = [o for o in objects if (o["path"] == req.get("path") if "path" in req
                       else o["properties"].get(req["property_name"]) == req["property_value"])
                       and (not req.get("class_name") or req["class_name"] in o["classes"])]
            if len(matches) != 1:
                return self.failure("AmbiguousObjectMatch" if matches else "ObjectNotFound")
            return {k: v for k, v in matches[0].items() if k != "properties"}
        obj = next((o for o in objects if o["oid"] == req.get("oid")), None)
        if action == "object_properties":
            return copy.deepcopy(obj["properties"]) if obj else self.failure("NotRegisteredObject")
        if action == "object_set_properties":
            obj["properties"].update(req["properties"])
        elif action == "action_trigger":
            self.objects["dialog"] = self.obj(50, "settingsDialog", ["QDialog", "QWidget", "QObject"])
        elif action == "widget_keyclick":
            obj["properties"]["text"] = obj["properties"].get("text", "") + req["text"]
        elif action == "shortcut" and req["keysequence"] == "Backspace":
            obj["properties"]["text"] = ""
        elif action == "widget_close":
            obj["properties"]["visible"] = False
        elif action == "model":
            return {"oid": 47, "path": "main/tree/model", "classes": ["QAbstractItemModel", "QObject"]}
        elif action == "model_items":
            return {"items": [{"modelid": 47, "row": 0, "column": 0, "value": "Folder",
                               "items": [{"modelid": 47, "row": 1, "column": 0, "itempath": "0-0",
                                          "value": "file.txt", "check_state": "checked"}]}]}
        elif action == "grab":
            return {"format": "PNG", "data": base64.b64encode(PNG).decode()}
        return {}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@pytest.fixture
def fake():
    server = FakeFunq()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
def funq_root():
    root = Path(os.environ.get("FUNQ_ROOT", Path(__file__).resolve().parents[2]))
    if not (root / "client" / "funq" / "client.py").is_file():
        pytest.fail("Set FUNQ_ROOT to the local Funq checkout before running adapter tests")
    return root


@pytest.fixture
def service(funq_root, tmp_path):
    instance = FunqService(funq_root, tmp_path / "artifacts")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def session(service, fake):
    return service.attach(fake.port, expected_class="CMainWindow")["session_id"]
