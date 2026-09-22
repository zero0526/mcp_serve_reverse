from typing import Any, Literal
from pydantic import BaseModel, Field


class SessionScope(BaseModel):
    session_id: str = Field(description="ID của phiên capture cần truy vấn")


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=500, description="Số lượng bản ghi tối đa")
    offset: int = Field(default=0, ge=0, description="Vị trí bắt đầu lấy dữ liệu")


class TimeRange(BaseModel):
    start_ns: int | None = Field(default=None, description="Thời điểm bắt đầu (nanoseconds)")
    end_ns: int | None = Field(default=None, description="Thời điểm kết thúc (nanoseconds)")


class StartCaptureRequest(BaseModel):
    source: Literal["browser", "android"] = Field(default="browser", description="Nguồn thu thập")
    name: str = Field(description="Tên phiên capture")
    target: str | None = Field(default=None, description="URL trang web hoặc package app")
    task_id: str | None = Field(default=None, description="Task ID liên kết")
    options: dict[str, Any] = Field(default_factory=dict, description="Tùy chọn trình duyệt/thiết bị")


class SearchTraceEventsRequest(SessionScope, Pagination, TimeRange):
    event_types: list[str] | None = Field(default=None, description="Danh sách event_type cần lọc")
    page_id: str | None = Field(default=None, description="Filter theo page_id")
    keyword: str | None = Field(default=None, description="Từ khóa tìm kiếm trong payload")


class GetTraceTimelineRequest(SessionScope, TimeRange):
    event_types: list[str] | None = Field(default=None, description="Lọc loại sự kiện")
    limit: int = Field(default=100, ge=1, le=500, description="Giới hạn số mốc timeline")


class GetGraphNodeRequest(SessionScope):
    node_id: str = Field(description="ID của GraphNode cần lấy")
    include_evidence: bool = Field(default=True, description="Kèm theo danh sách bằng chứng")


class GetGraphNeighborsRequest(SessionScope):
    node_id: str = Field(description="ID của node trung tâm")
    direction: Literal["in", "out", "both"] = Field(default="both", description="Hướng duyệt cạnh")
    edge_types: list[str] | None = Field(default=None, description="Lọc theo RelationType")
    min_confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Độ tin cậy tối thiểu")
    limit: int = Field(default=100, ge=1, le=500, description="Số neighbor tối đa")


class GetGraphStatisticsRequest(SessionScope):
    include_edge_distribution: bool = Field(default=True, description="Bao gồm phân bố loại cạnh")
    include_orphans: bool = Field(default=True, description="Đếm số lượng orphan nodes")


class TraceOriginRequest(SessionScope):
    target_node_id: str = Field(description="ID node mục tiêu cần truy vết nguồn gốc")
    max_depth: int = Field(default=10, ge=1, le=50, description="Độ sâu duyệt tối đa")
    max_paths: int = Field(default=20, ge=1, le=100, description="Số đường dẫn tối đa")
    min_confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Độ tin cậy tối thiểu")
    include_heuristics: bool = Field(default=False, description="Kèm theo các quan hệ heuristic")


class TraceDownstreamRequest(SessionScope):
    source_node_id: str = Field(description="ID node xuất phát cần tìm nơi sử dụng")
    max_depth: int = Field(default=10, ge=1, le=50, description="Độ sâu duyệt tối đa")
    max_nodes: int = Field(default=200, ge=1, le=500, description="Số node tối đa")
    min_confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Độ tin cậy tối thiểu")


class ExplainLineagePathRequest(SessionScope):
    path_id: str = Field(description="ID đường dẫn lineage cần giải thích")
    target_node_id: str | None = Field(default=None, description="Node mục tiêu nếu không có path_id")


class CompareLineageRequest(BaseModel):
    left_session_id: str = Field(description="Session ID bên trái")
    left_node_id: str = Field(description="Node ID bên trái")
    right_session_id: str = Field(description="Session ID bên phải")
    right_node_id: str = Field(description="Node ID bên phải")
    comparison_mode: Literal["structure", "source", "transformation"] = Field(default="structure")


class SummarizeRequestRequest(SessionScope):
    request_id: str = Field(description="ID của HTTP Request")
    include_headers: bool = Field(default=True, description="Kèm headers")
    include_response: bool = Field(default=True, description="Kèm response")
    redaction_mode: Literal["strict", "standard", "debug"] = Field(default="strict")


class AnalyzeRequestLineageRequest(SessionScope):
    request_id: str = Field(description="ID của HTTP Request")
    min_confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class FindRequestDependenciesRequest(SessionScope):
    request_id: str = Field(description="ID của HTTP Request")
    include_storage: bool = Field(default=True)
    include_executions: bool = Field(default=True)
    max_depth: int = Field(default=10, ge=1, le=30)


class CompareRequestsRequest(BaseModel):
    left_session_id: str
    left_request_id: str
    right_session_id: str
    right_request_id: str
    redaction_mode: Literal["strict", "standard", "debug"] = Field(default="strict")
