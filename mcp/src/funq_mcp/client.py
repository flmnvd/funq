"""Use Funq's client models with bounded, deadline-aware TCP framing."""

import importlib
import json
import socket
import sys
import time
from pathlib import Path

from .errors import AdapterError


def reject_constant(value):
    raise ValueError("Non-finite JSON value in Funq response: " + value)


def create_client(funq_root, host, port, timeout, max_frame_bytes=32 * 1024 * 1024):
    client_dir = Path(funq_root).resolve() / "client"
    if not (client_dir / "funq" / "client.py").is_file():
        raise AdapterError("MissingFunqClient", "Set --funq-root to the Funq checkout.", path=str(client_dir))
    if str(client_dir) not in sys.path:
        sys.path.insert(0, str(client_dir))
    module = importlib.import_module("funq.client")
    if Path(module.__file__).resolve().parent != client_dir / "funq":
        raise AdapterError("FunqImportConflict", "A different Funq client was already imported.")

    class BoundedClient(module.FunqClient):
        # Inherit lookup/model APIs; bypass the original buffered socket reader,
        # which can leave partial frames buffered after a timeout.
        def __init__(self):
            self._socket = None
            self.deadline = None
            self.commands = None
            self.aliases = module.HooqAliases()
            self.request_timeout = timeout
            self.max_frame_bytes = max_frame_bytes
            self._socket = socket.create_connection((host, port), timeout=timeout)
            self.endpoint = self._socket.getpeername()[:2]

        @property
        def connected(self):
            return self._socket is not None

        def close(self):
            sock, self._socket = self._socket, None
            if sock is not None:
                sock.close()

        def _set_timeout(self):
            remaining = self.request_timeout
            if self.deadline is not None:
                remaining = min(remaining, self.deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError("Funq operation deadline expired")
            self._socket.settimeout(remaining)

        def _receive(self, size):
            parts = []
            while size:
                self._set_timeout()
                part = self._socket.recv(min(size, 65536))
                if not part:
                    raise EOFError("Funq connection closed before the complete response arrived")
                parts.append(part)
                size -= len(part)
            return b"".join(parts)

        def send_command(self, action, **kwargs):
            if self.commands is not None and action not in self.commands:
                raise AdapterError("UnsupportedCommand", "The attached Funq plugin lacks this command.", action=action)
            if self._socket is None:
                raise AdapterError("SessionDisconnected", "Attach again before issuing more commands.")
            body = json.dumps({**kwargs, "action": action}, ensure_ascii=True, allow_nan=False).encode("utf-8")
            if len(body) > self.max_frame_bytes:
                raise AdapterError("RequestTooLarge", "The Funq request exceeds the configured frame limit.")
            attempted = False
            try:
                self._set_timeout()
                attempted = True
                self._socket.sendall(str(len(body)).encode("ascii") + b"\n" + body)
                header = bytearray()
                while True:
                    byte = self._receive(1)
                    if byte == b"\n":
                        break
                    if len(header) >= 20 or not b"0" <= byte <= b"9":
                        raise ValueError("Invalid Funq frame length header")
                    header.extend(byte)
                size = int(header)
                if not 0 < size <= self.max_frame_bytes:
                    raise ValueError("Funq response frame exceeds the configured size limit")
                response = json.loads(self._receive(size).decode("utf-8"), parse_constant=reject_constant)
                if not isinstance(response, dict) or "event" in response:
                    raise ValueError("Expected a Funq command response, received an unsolicited event or invalid JSON")
            except (OSError, EOFError, ValueError) as error:
                self.close()
                code = "RequestTimeout" if isinstance(error, TimeoutError) else "ConnectionLost"
                if isinstance(error, ValueError):
                    code = "ProtocolError"
                raise AdapterError(code, str(error), action=action, request_attempted=attempted,
                                   outcome="unknown" if attempted else "not_sent", reattach_required=True) from error
            if response.get("success") is False:
                raise module.FunqError(response.get("errName", "FunqError"), response.get("errDesc", ""))
            return response

    return BoundedClient()
