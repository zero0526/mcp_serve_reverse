import time
from typing import Any

from app.adapters.browser.browser_session import BrowserSession
from app.application.ingest.ingest_event import IngestEventUseCase
from app.domain.shared.enums import SessionStatus
from app.domain.trace.value_objects import PreSeedState
from app.ports.repositories import SessionRepositoryPort


class StartSessionUseCase:
    """Use case khởi động một capture session có hỗ trợ pre-seed state và task grouping."""

    def __init__(
        self,
        session_repository: SessionRepositoryPort,
        ingest_use_case: IngestEventUseCase,
    ):
        self.session_repo = session_repository
        self.ingest_use_case = ingest_use_case
        self.active_browsers: dict[str, BrowserSession] = {}

    async def execute(
        self,
        session_id: str,
        name: str | None = None,
        target: str | None = None,
        task_id: str | None = None,
        pre_seed_state: PreSeedState | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 1. Tạo session trong cơ sở dữ liệu
        meta: dict[str, Any] = {}
        if pre_seed_state:
            meta["has_pre_seed"] = True
            meta["pre_seed_cookies_count"] = len(pre_seed_state.cookies)
            meta["pre_seed_storage_keys"] = list(pre_seed_state.storage.local_storage.keys())

        session_record = await self.session_repo.create(
            session_id=session_id,
            name=name,
            target=target,
            source="browser",
            task_id=task_id,
            metadata=meta,
        )

        # 2. Khởi tạo BrowserSession gắn với IngestEventUseCase
        browser_session = BrowserSession(
            event_consumer=self.ingest_use_case.execute,
            headless=(options or {}).get("headless", True),
        )
        self.active_browsers[session_id] = browser_session

        # 3. Bật trình duyệt, tiêm pre-seed và instrumentation
        await self.session_repo.update_status(session_id, SessionStatus.STARTING)
        await browser_session.start(
            session_id=session_id,
            target=target,
            pre_seed_state=pre_seed_state,
            options=options,
        )
        await self.session_repo.update_status(session_id, SessionStatus.RUNNING)

        return {
            "session_id": session_id,
            "task_id": task_id,
            "status": SessionStatus.RUNNING.value,
            "target": target,
            "browser_ready": True,
        }
