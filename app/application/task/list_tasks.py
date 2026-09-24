from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository
from app.domain.task.entities import Task, TaskStatus
from app.ports.task_repository import TaskRepositoryPort


class ListTasksUseCase:
    """Use case liệt kê danh sách Task có phân trang và lọc theo status."""

    def __init__(
        self,
        task_repository: TaskRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.task_repo = task_repository or SQLiteTaskRepository(session_factory=session_factory)

    async def execute(
        self,
        status: TaskStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        return await self.task_repo.list_all(status=status, limit=limit, offset=offset)
