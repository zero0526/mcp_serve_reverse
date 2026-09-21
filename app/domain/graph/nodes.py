import time
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator


class NodeType(str, Enum):
    def __str__(self) -> str:
        return str(self.value)

    SESSION = "session"
    FUNCTION_DEFINITION = "function_definition"
    FUNCTION_EXECUTION = "function_execution"
    VARIABLE = "variable"
    VALUE = "value"
    TRANSFORMATION = "transformation"
    HTTP_REQUEST = "http_request"
    HTTP_RESPONSE = "http_response"
    HEADER = "header"
    QUERY_PARAMETER = "query_parameter"
    BODY_FIELD = "body_field"
    STORAGE = "storage"
    STORAGE_ENTRY = "storage_entry"
    CRYPTO_OPERATION = "crypto_operation"


class GraphNode(BaseModel):
    """Entity đại diện cho một đỉnh (Node) trong Property Graph."""

    id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    node_type: NodeType | str
    label: str | None = None
    entity_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at_ns: int = Field(default_factory=time.time_ns)

    @field_validator("node_type", mode="before")
    @classmethod
    def normalize_node_type(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        s = str(v)
        if s.startswith("NodeType."):
            return s.split(".", 1)[1].lower()
        return s