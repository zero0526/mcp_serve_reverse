from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository
from app.domain.task.entities import TaskStatus
from app.ports.task_repository import TaskRepositoryPort


class UpdateTaskUseCase:
    """Use case cập nhật trạng thái Task và metadata ghi chú."""

    def __init__(
        self,
        task_repository: TaskRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.task_repo = task_repository or SQLiteTaskRepository(session_factory=session_factory)

    async def execute(
        self,
        task_id: str,
        status: TaskStatus | str,
        metadata_update: dict[str, Any] | None = None,
    ) -> bool:
        return await self.task_repo.update_status(
            task_id=task_id, status=status, metadata_update=metadata_update
        )
