"""Selectors are resolved for each operation; raw pointer IDs stay internal."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Selector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(default=None, min_length=1, description="Complete Funq object path.")
    object_name: str | None = Field(default=None, min_length=1, description="Exact Qt objectName, including namespaces.")
    class_name: str | None = Field(default=None, min_length=1, description="Qt class filter for an object_name lookup.")

    @model_validator(mode="after")
    def validate_lookup(self):
        if bool(self.path) == bool(self.object_name):
            raise ValueError("Specify exactly one of path or object_name")
        if self.path and self.class_name:
            raise ValueError("class_name is supported only with object_name")
        return self

    def command(self):
        if self.path:
            return {"path": self.path}
        fields = {"property_name": "objectName", "property_value": self.object_name}
        if self.class_name:
            fields["class_name"] = self.class_name
        return fields
