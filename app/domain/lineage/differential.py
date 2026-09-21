from typing import Any
from pydantic import BaseModel, Field

from app.domain.lineage.entities import ParameterType


class FieldVariance(BaseModel):
    """Mô tả sự biến thiên của một trường dữ liệu qua các Session."""

    path: str  # Ví dụ: "body.name", "headers.authorization", "query.tab"
    param_type: ParameterType
    values_per_session: dict[str, Any] = Field(default_factory=dict)
    is_constant: bool = False
    inferred_purpose: str | None = None
    notes: str | None = None


class SessionComparisonResult(BaseModel):
    """Kết quả phân tích so sánh vi phân giữa 2 hoặc nhiều Session trong cùng Task."""

    task_id: str
    session_ids: list[str]
    variances: list[FieldVariance] = Field(default_factory=list)
    classified_variables: list[str] = Field(default_factory=list)  # Các biến cần truyền vào khi replay
    classified_tokens: list[str] = Field(default_factory=list)     # Các token phụ thuộc phiên
    classified_constants: list[str] = Field(default_factory=list)  # Các tham số cố định
    summary: dict[str, int] = Field(default_factory=dict)
