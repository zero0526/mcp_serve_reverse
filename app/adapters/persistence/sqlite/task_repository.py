import time
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import SessionModel, TaskModel
from app.domain.task.entities import BrowserConfig, Task, TaskStatus
from app.infrastructure.serialization.json import safe_dumps, safe_loads
from app.ports.task_repository import TaskRepositoryPort


class SQLiteTaskRepository(TaskRepositoryPort):
    """Triển khai lưu trữ Task trong SQLite."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    def _to_entity(self, model: TaskModel) -> Task:
        env_vars = safe_loads(model.env_vars_json) if model.env_vars_json else {}
        initial_urls = safe_loads(model.initial_urls_json) if model.initial_urls_json else []
        b_cfg_dict = safe_loads(model.browser_config_json) if model.browser_config_json else {}
        metadata = safe_loads(model.metadata_json) if model.metadata_json else {}

        # Trích xuất session_ids an toàn tránh DetachedInstanceError
        session_ids = []
        if "sessions" in model.__dict__ and model.__dict__["sessions"]:
            session_ids = [s.id for s in model.__dict__["sessions"]]

        return Task(
            id=model.id,
            name=model.name,
            goal_description=model.goal_description,
            instructions=model.instructions,
            env_vars=env_vars,
            initial_urls=initial_urls,
            browser_config=BrowserConfig(**b_cfg_dict),
            status=TaskStatus(model.status) if model.status in TaskStatus._value2member_map_ else TaskStatus.CREATED,
            session_ids=session_ids,
            created_at_ns=model.created_at_ns,
            updated_at_ns=model.updated_at_ns,
            metadata=metadata,
        )

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
        now_ns = time.time_ns()
        task_model = TaskModel(
            id=task_id,
            name=name,
            goal_description=goal_description,
            instructions=instructions,
            env_vars_json=safe_dumps(env_vars or {}),
            initial_urls_json=safe_dumps(initial_urls or []),
            browser_config_json=safe_dumps(browser_config or {}),
            status=TaskStatus.CREATED.value,
            created_at_ns=now_ns,
            updated_at_ns=now_ns,
            metadata_json=safe_dumps(metadata or {}),
        )

        async with self.session_factory() as db:  # type: AsyncSession
            db.add(task_model)
            await db.commit()
            return self._to_entity(task_model)

    async def get_by_id(self, task_id: str) -> Task | None:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = (
                select(TaskModel)
                .options(selectinload(TaskModel.sessions))
                .where(TaskModel.id == task_id)
            )
            res = await db.execute(stmt)
            obj = res.scalar_one_or_none()
            if not obj:
                return None
            return self._to_entity(obj)

    async def list_all(
        self,
        status: TaskStatus | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = (
                select(TaskModel)
                .options(selectinload(TaskModel.sessions))
                .order_by(TaskModel.created_at_ns.desc())
                .limit(limit)
                .offset(offset)
            )
            if status:
                status_val = status.value if isinstance(status, TaskStatus) else str(status)
                stmt = stmt.where(TaskModel.status == status_val)

            res = await db.execute(stmt)
            records = res.scalars().all()
            return [self._to_entity(r) for r in records]

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        metadata_update: dict[str, Any] | None = None,
    ) -> bool:
        status_val = status.value if isinstance(status, TaskStatus) else str(status)
        now_ns = time.time_ns()

        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(TaskModel).where(TaskModel.id == task_id)
            res = await db.execute(stmt)
            obj = res.scalar_one_or_none()
            if not obj:
                return False

            obj.status = status_val
            obj.updated_at_ns = now_ns
            if metadata_update:
                curr_meta = safe_loads(obj.metadata_json) if obj.metadata_json else {}
                curr_meta.update(metadata_update)
                obj.metadata_json = safe_dumps(curr_meta)

            await db.commit()
            return True

    async def add_session_to_task(self, task_id: str, session_id: str) -> bool:
        async with self.session_factory() as db:  # type: AsyncSession
            # Cập nhật task_id trong SessionModel
            stmt = select(SessionModel).where(SessionModel.id == session_id)
            res = await db.execute(stmt)
            sess = res.scalar_one_or_none()
            if not sess:
                return False

            sess.task_id = task_id
            await db.commit()
            return True
