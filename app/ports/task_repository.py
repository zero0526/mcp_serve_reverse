from abc import ABC, abstractmethod
from typing import Any

from app.domain.task.entities import Task, TaskStatus


class TaskRepositoryPort(ABC):
    """Port trừu tượng cho việc lưu trữ và truy vấn Task."""

    @abstractmethod
    async def create(
        self,
        task_id: str,
        name: str,
        goal_description: str = "",
        instructions: str = "",
        env_vars: dict[str, Any] | None = None,
        initial_urls: list[str] | None = None,
        browser_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Tạo mới một Task."""
        pass

    @abstractmethod
    async def get_by_id(self, task_id: str) -> Task | None:
        """Lấy thông tin chi tiết của một Task kèm danh sách session_ids."""
        pass

    @abstractmethod
    async def list_all(
        self,
        status: TaskStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """Liệt kê danh sách Tasks có phân trang và lọc theo trạng thái."""
        pass

    @abstractmethod
    async def update_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        metadata_update: dict[str, Any] | None = None,
    ) -> bool:
        """Cập nhật trạng thái và metadata của Task."""
        pass

    @abstractmethod
    async def add_session_to_task(self, task_id: str, session_id: str) -> bool:
        """Liên kết một Session với Task."""
        pass
