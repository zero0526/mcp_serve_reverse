from typing import Any

from app.ports.repositories import SessionRepositoryPort


class CaptureStatusUseCase:
    """Use case truy vấn trạng thái chi tiết theo Session hoặc theo Task."""

    def __init__(self, session_repository: SessionRepositoryPort):
        self.session_repo = session_repository

    async def get_session_status(self, session_id: str) -> dict[str, Any] | None:
        session_info = await self.session_repo.get_by_id(session_id)
        if not session_info:
            return None

        stats = await self.session_repo.get_statistics(session_id)
        session_info["statistics"] = stats
        return session_info

    async def get_task_sessions(self, task_id: str) -> list[dict[str, Any]]:
        """Lấy danh sách và thống kê toàn bộ các session thuộc về một Task."""
        sessions = await self.session_repo.get_by_task_id(task_id)
        for s in sessions:
            s["statistics"] = await self.session_repo.get_statistics(s["id"])
        return sessions
