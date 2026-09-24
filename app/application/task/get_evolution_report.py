from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.session_log_repository import SQLiteSessionLogRepository
from app.ports.session_log_repository import SessionLogRepositoryPort


class GetToolEvolutionReportUseCase:
    """Use case tổng hợp báo cáo tiến hóa MCP Tools từ các nhật ký hồi cứu của Agent."""

    def __init__(
        self,
        session_log_repository: SessionLogRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.log_repo = session_log_repository or SQLiteSessionLogRepository(session_factory=session_factory)

    async def execute(self, task_id: str | None = None) -> dict[str, Any]:
        return await self.log_repo.get_evolution_summary(task_id=task_id)
