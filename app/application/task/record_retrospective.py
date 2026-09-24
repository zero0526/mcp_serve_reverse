import uuid
from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.session_log_repository import SQLiteSessionLogRepository
from app.domain.task.retro_entities import LogType, SessionLog
from app.ports.session_log_repository import SessionLogRepositoryPort


class RecordTaskRetrospectiveUseCase:
    """Use case ghi nhận phản hồi hồi cứu của Agent về MCP tools sau khi thực hiện Task."""

    def __init__(
        self,
        session_log_repository: SessionLogRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.log_repo = session_log_repository or SQLiteSessionLogRepository(session_factory=session_factory)

    async def execute(
        self,
        task_id: str,
        agent_evaluation: str,
        missing_tools: list[str] | None = None,
        suggested_tools: list[dict[str, Any]] | None = None,
        bottlenecks: list[str] | None = None,
        efficiency_rating: int = 5,
        session_id: str | None = None,
        log_type: LogType | str = LogType.RETROSPECTIVE,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLog:
        log_id = f"log_{uuid.uuid4().hex[:10]}"
        return await self.log_repo.create(
            log_id=log_id,
            task_id=task_id,
            agent_evaluation=agent_evaluation,
            session_id=session_id,
            log_type=log_type,
            missing_tools=missing_tools or [],
            suggested_tools=suggested_tools or [],
            bottlenecks=bottlenecks or [],
            efficiency_rating=max(1, min(efficiency_rating, 5)),
            metadata=metadata,
        )
