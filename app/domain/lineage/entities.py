from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ParameterType(str, Enum):
    def __str__(self) -> str:
        return str(self.value)

    CONSTANT = "constant"
    USER_INPUT = "user_input"
    SESSION_TOKEN = "session_token"
    TIMESTAMP = "timestamp"
    EPHEMERAL_NONCE = "ephemeral_nonce"
    UNKNOWN = "unknown"


class LineageStep(BaseModel):
    """Một bước cụ thể trên đường đi dữ liệu (Data Lineage Step)."""

    step_number: int
    from_node_id: str
    to_node_id: str
    relation: str
    action_description: str
    confidence: float = 1.0
    evidence_refs: list[str] = Field(default_factory=list)


class LineagePath(BaseModel):
    """Chuỗi các bước lần vết nguồn gốc từ Origin tới Sink."""

    target_node_id: str
    target_param: str
    origin_node_id: str
    origin_type: str  # storage, cookie, response, user_input, hardcoded
    origin_key: str | None = None
    steps: list[LineageStep] = Field(default_factory=list)
    overall_confidence: float = 1.0
    status: str = "CONFIRMED"  # CONFIRMED | SUPPORTED_INFERENCE | HYPOTHESIS


class ReplayStepSpec(BaseModel):
    """Đặc tả một bước trong quy trình replay tự động."""

    order: int
    step_type: str  # read_storage, seed_cookie, http_request
    target_id: str
    action: str
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    output_bindings: dict[str, str] = Field(default_factory=dict)


class ReplaySpec(BaseModel):
    """Hợp đồng bàn giao hoàn chỉnh cho Phase 3 (Replay & Synthesis Engine)."""

    task_id: str
    target_request_id: str
    method: str
    url_template: str
    headers_template: dict[str, str] = Field(default_factory=dict)
    body_template: Any = None
    required_variables: list[str] = Field(default_factory=list)
    session_prerequisites: list[ReplayStepSpec] = Field(default_factory=list)
    parameter_lineages: dict[str, LineagePath] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
