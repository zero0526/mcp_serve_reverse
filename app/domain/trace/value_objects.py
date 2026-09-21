from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

from app.domain.trace.events import EventType


class CookieSeed(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    http_only: bool = False
    secure: bool = False
    same_site: Literal["Strict", "Lax", "None"] = "Lax"


class StorageSeed(BaseModel):
    local_storage: dict[str, str] = Field(default_factory=dict)
    session_storage: dict[str, str] = Field(default_factory=dict)


class PreSeedState(BaseModel):
    cookies: list[CookieSeed] = Field(default_factory=list)
    storage: StorageSeed = Field(default_factory=StorageSeed)
    storage_state_path: str | None = None


class EventEnvelope(BaseModel):
    event_id: str = Field(min_length=1, max_length=256)
    schema_version: int = Field(default=1, ge=1)

    session_id: str
    source: str = "browser"
    event_type: EventType | str

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        s = str(v)
        if s.startswith("EventType."):
            return s.split(".", 1)[1].lower()
        return s

    timestamp_ns: int = Field(ge=0)
    sequence: int | None = Field(default=None, ge=0)

    page_id: str | None = None
    frame_id: str | None = None

    execution_id: str | None = None
    parent_execution_id: str | None = None

    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
