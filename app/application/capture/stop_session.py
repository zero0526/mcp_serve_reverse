import time
from typing import Any

from app.adapters.browser.browser_session import BrowserSession
from app.domain.shared.enums import SessionStatus
from app.ports.repositories import SessionRepositoryPort


class StopSessionUseCase:
    """Use case dừng một capture session, giải phóng browser và chốt thống kê."""

    def __init__(
        self,
        session_repository: SessionRepositoryPort,
        active_browsers: dict[str, BrowserSession],
    ):
        self.session_repo = session_repository
        self.active_browsers = active_browsers

    async def execute(self, session_id: str) -> dict[str, Any]:
        # 1. Cập nhật trạng thái stopping
        await self.session_repo.update_status(session_id, SessionStatus.STOPPING)

        # 2. Dừng browser nếu đang chạy
        browser = self.active_browsers.pop(session_id, None)
        if browser:
            await browser.stop()

        # 3. Chốt kết thúc session
        now_ns = time.time_ns()
        stats = await self.session_repo.get_statistics(session_id)
        await self.session_repo.update_status(
            session_id=session_id,
            status=SessionStatus.STOPPED,
            ended_at_ns=now_ns,
            metadata_update={"statistics": stats},
        )

        return {
            "session_id": session_id,
            "status": SessionStatus.STOPPED.value,
            "statistics": stats,
        }
