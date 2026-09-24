from abc import ABC, abstractmethod
from typing import Any

from app.domain.task.retro_entities import LogType, SessionLog


class SessionLogRepositoryPort(ABC):
    """Port trừu tượng cho việc ghi nhận và truy vấn Session / Task retrospective logs."""

    @abstractmethod
    async def create(
        self,
        log_id: str,
        task_id: str,
        agent_evaluation: str,
        session_id: str | None = None,
        log_type: LogType | str = LogType.RETROSPECTIVE,
        missing_tools: list[str] | None = None,
        suggested_tools: list[dict[str, Any]] | None = None,
        bottlenecks: list[str] | None = None,
        efficiency_rating: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLog:
        """Tạo một log hồi cứu / đánh giá công cụ mới."""
        pass

    @abstractmethod
    async def list_by_task_id(
        self,
        task_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionLog]:
        """Lấy danh sách các logs của một task cụ thể."""
        pass

    @abstractmethod
    async def list_all(
        self,
        log_type: LogType | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionLog]:
        """Liệt kê tất cả logs của hệ thống để phân tích tiến hóa công cụ."""
        pass

    @abstractmethod
    async def get_evolution_summary(self, task_id: str | None = None) -> dict[str, Any]:
        """Tổng hợp thống kê các tool còn thiếu và đề xuất cải tiến."""
        pass
