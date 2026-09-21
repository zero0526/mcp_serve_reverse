import time
from typing import Any
from pydantic import BaseModel, Field, field_validator

from app.domain.graph.relations import RelationType


class EdgeEvidence(BaseModel):
    """Bằng chứng chứng minh cho quan hệ của Graph Edge."""

    id: int | None = None
    edge_id: int | None = None
    evidence_type: str = "observed_event"
    source_event_id: str | None = None
    confidence: float | None = 1.0
    explanation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Cạnh (Edge) nối giữa hai Node trong đồ thị quan hệ."""

    id: int | None = None
    session_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    relation_type: RelationType | str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_status: str = "observed"
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at_ns: int = Field(default_factory=time.time_ns)
    evidence_list: list[EdgeEvidence] = Field(default_factory=list)

    @field_validator("relation_type", mode="before")
    @classmethod
    def normalize_relation_type(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        s = str(v)
        if s.startswith("RelationType."):
            return s.split(".", 1)[1].upper()
        return s.upper()
