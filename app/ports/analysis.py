from typing import Protocol

from app.domain.lineage.differential import SessionComparisonResult
from app.domain.lineage.entities import LineagePath, ReplaySpec


class LineageServicePort(Protocol):
    """Port cung cấp các dịch vụ phân tích Lineage và so sánh đa phiên."""

    async def trace_backward(
        self,
        session_id: str,
        target_node_id: str,
        param_name: str | None = None,
    ) -> LineagePath | None:
        """Truy vết ngược tìm nguồn gốc của một node hoặc tham số."""
        ...

    async def trace_forward(
        self,
        session_id: str,
        origin_node_id: str,
    ) -> list[LineagePath]:
        """Truy vết xuôi xem node nguồn lan truyền tới các node nào."""
        ...

    async def compare_sessions(
        self,
        task_id: str,
    ) -> SessionComparisonResult:
        """So sánh vi phân giữa các session thuộc cùng một task_id."""
        ...

    async def generate_replay_spec(
        self,
        task_id: str,
        target_request_id: str,
    ) -> ReplaySpec:
        """Tạo đặc tả ReplaySpec sẵn sàng bàn giao cho Phase 3."""
        ...
