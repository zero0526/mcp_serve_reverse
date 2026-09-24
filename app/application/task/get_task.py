from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository
from app.domain.task.entities import Task
from app.ports.task_repository import TaskRepositoryPort


class GetTaskUseCase:
    """Use case lấy chi tiết Task và các Session liên kết."""

    def __init__(
        self,
        task_repository: TaskRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.task_repo = task_repository or SQLiteTaskRepository(session_factory=session_factory)

    async def execute(self, task_id: str) -> Task | None:
        return await self.task_repo.get_by_id(task_id)
