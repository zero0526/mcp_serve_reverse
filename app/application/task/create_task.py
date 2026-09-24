import uuid
from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository
from app.domain.task.entities import Task
from app.ports.repositories import SessionRepositoryPort
from app.ports.task_repository import TaskRepositoryPort


class CreateTaskUseCase:
    """Use case tạo mới một Task và tự động khởi tạo các Session tương ứng với initial_urls."""

    def __init__(
        self,
        task_repository: TaskRepositoryPort | None = None,
        session_repository: SessionRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.task_repo = task_repository or SQLiteTaskRepository(session_factory=session_factory)
        self.session_repo = session_repository or SQLiteSessionRepository(session_factory=session_factory)

    async def execute(
        self,
        name: str,
        goal_description: str = "",
        instructions: str = "",
        env_vars: dict[str, Any] | None = None,
        initial_urls: list[str] | None = None,
        browser_config: dict[str, Any] | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        tid = task_id or f"task_{uuid.uuid4().hex[:8]}"
        urls = initial_urls or []

        # 1. Tạo task entity trong SQLite
        task = await self.task_repo.create(
            task_id=tid,
            name=name,
            goal_description=goal_description,
            instructions=instructions,
            env_vars=env_vars,
            initial_urls=urls,
            browser_config=browser_config,
            metadata=metadata,
        )

        # 2. Với mỗi initial_url, khởi tạo sẵn 1 Session trong SessionRepository
        session_ids: list[str] = []
        for idx, url in enumerate(urls, start=1):
            sid = f"sess_{tid}_{idx}"
            sess_meta = {
                "task_id": tid,
                "url_index": idx,
                "browser_config": browser_config or {},
            }
            await self.session_repo.create(
                session_id=sid,
                name=f"{name} - Session {idx}",
                target=url,
                source="browser",
                task_id=tid,
                metadata=sess_meta,
            )
            await self.task_repo.add_session_to_task(task_id=tid, session_id=sid)
            session_ids.append(sid)

        # Cập nhật danh sách session_ids vào task entity trả về
        task.session_ids = session_ids
        return task
