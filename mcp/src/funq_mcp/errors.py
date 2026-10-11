"""Errors that can be returned to an MCP client without losing context."""


class AdapterError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self):
        return {"code": self.code, "message": str(self), **self.details}
