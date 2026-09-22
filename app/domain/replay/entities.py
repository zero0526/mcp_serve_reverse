from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ReplayMode(str, Enum):
    def __str__(self) -> str:
        return str(self.value)

    DRY_RUN = "dry_run"
    EXECUTE = "execute"
    EXPLORATORY = "exploratory"


class ReplayRequest(BaseModel):
    """Mô hình đại diện cho một HTTP request đã được chuẩn bị sẵn sàng thực thi."""

    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    cookies: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 30.0


class ReplayExecutionResult(BaseModel):
    """Kết quả phản hồi sau khi phát lại HTTP request."""

    request_id: str
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    latency_ms: float = 0.0
    success: bool = True
    error_message: str | None = None


class ReplayComparison(BaseModel):
    """Đánh giá so sánh phản hồi thực tế so với capture gốc."""

    target_request_id: str
    status_match: bool
    expected_status: int
    actual_status: int
    header_diffs: list[str] = Field(default_factory=list)
    body_diffs: list[str] = Field(default_factory=list)
    match_score: float = 1.0


class SynthesizedCode(BaseModel):
    """Mã nguồn đã được sinh tự động kèm chú thích nguồn gốc tham số."""

    task_id: str
    target_request_id: str
    language: str  # python, curl, typescript
    code: str
    variables: list[str] = Field(default_factory=list)
    description: str = ""
