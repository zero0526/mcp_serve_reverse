import time
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    NetworkRequestModel,
    NetworkResponseModel,
    SessionModel,
    StorageOperationModel,
    TaskModel,
    TraceEventModel,
)
from app.domain.shared.enums import SessionStatus
from app.infrastructure.serialization.json import safe_dumps, safe_loads
from app.ports.repositories import SessionRepositoryPort


class SQLiteSessionRepository(SessionRepositoryPort):
    """Repository quản lý phiên Session trong SQLite."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    async def create(
        self,
        session_id: str,
        name: str | None,
        target: str | None,
        source: str = "browser",
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = metadata or {}
        if task_id:
            meta["task_id"] = task_id

        now_ns = time.time_ns()
        async with self.session_factory() as db:  # type: AsyncSession
            if task_id:
                # Đảm bảo task_id tồn tại để không vi phạm Foreign Key constraint
                stmt_t = select(TaskModel.id).where(TaskModel.id == task_id)
                t_exists = (await db.execute(stmt_t)).scalar_one_or_none()
                if not t_exists:
                    db.add(
                        TaskModel(
                            id=task_id,
                            name=f"Task {task_id}",
                            goal_description="Auto-created task wrapper for session",
                            instructions="",
                            created_at_ns=now_ns,
                            updated_at_ns=now_ns,
                        )
                    )
                    await db.flush()

            stmt_s = select(SessionModel).where(SessionModel.id == session_id)
            existing_sess = (await db.execute(stmt_s)).scalar_one_or_none()
            if existing_sess:
                if name:
                    existing_sess.name = name
                if target:
                    existing_sess.target = target
                if task_id:
                    existing_sess.task_id = task_id
                existing_sess.updated_at_ns = now_ns
                if meta:
                    curr_meta = safe_loads(existing_sess.metadata_json) if existing_sess.metadata_json else {}
                    curr_meta.update(meta)
                    existing_sess.metadata_json = safe_dumps(curr_meta)
                await db.commit()
                return {
                    "id": session_id,
                    "source": existing_sess.source,
                    "name": existing_sess.name,
                    "target": existing_sess.target,
                    "status": existing_sess.status,
                    "task_id": existing_sess.task_id,
                    "started_at_ns": existing_sess.started_at_ns,
                    "metadata": safe_loads(existing_sess.metadata_json) if existing_sess.metadata_json else {},
                }

            session_obj = SessionModel(
                id=session_id,
                task_id=task_id,
                source=source,
                name=name,
                target=target,
                status=SessionStatus.CREATED.value,
                started_at_ns=now_ns,
                created_at_ns=now_ns,
                updated_at_ns=now_ns,
                metadata_json=safe_dumps(meta),
            )
            db.add(session_obj)
            await db.commit()

        return {
            "id": session_id,
            "source": source,
            "name": name,
            "target": target,
            "status": SessionStatus.CREATED.value,
            "task_id": task_id,
            "started_at_ns": now_ns,
        }

    async def update_status(
        self,
        session_id: str,
        status: SessionStatus | str,
        ended_at_ns: int | None = None,
        metadata_update: dict[str, Any] | None = None,
    ) -> None:
        now_ns = time.time_ns()
        val_status = status.value if isinstance(status, SessionStatus) else str(status)

        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(SessionModel).where(SessionModel.id == session_id)
            res = await db.execute(stmt)
            session_obj = res.scalar_one_or_none()
            if not session_obj:
                return

            session_obj.status = val_status
            session_obj.updated_at_ns = now_ns
            if ended_at_ns:
                session_obj.ended_at_ns = ended_at_ns

            if metadata_update:
                curr_meta = safe_loads(session_obj.metadata_json) if session_obj.metadata_json else {}
                curr_meta.update(metadata_update)
                session_obj.metadata_json = safe_dumps(curr_meta)

            await db.commit()

    async def get_by_id(self, session_id: str) -> dict[str, Any] | None:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(SessionModel).where(SessionModel.id == session_id)
            res = await db.execute(stmt)
            obj = res.scalar_one_or_none()
            if not obj:
                return None

            meta = safe_loads(obj.metadata_json) if obj.metadata_json else {}
            return {
                "id": obj.id,
                "source": obj.source,
                "name": obj.name,
                "target": obj.target,
                "status": obj.status,
                "task_id": obj.task_id or meta.get("task_id"),
                "started_at_ns": obj.started_at_ns,
                "ended_at_ns": obj.ended_at_ns,
                "created_at_ns": obj.created_at_ns,
                "updated_at_ns": obj.updated_at_ns,
                "metadata": meta,
            }

    async def get_by_task_id(self, task_id: str) -> list[dict[str, Any]]:
        """Lấy tất cả sessions thuộc về 1 Task để phục vụ so sánh vi phân."""
        async with self.session_factory() as db:  # type: AsyncSession
            # SQLite json_extract metadata_json -> $.task_id
            stmt = select(SessionModel).order_by(SessionModel.started_at_ns.asc())
            res = await db.execute(stmt)
            sessions = res.scalars().all()

            results = []
            for obj in sessions:
                meta = safe_loads(obj.metadata_json) if obj.metadata_json else {}
                if meta.get("task_id") == task_id:
                    results.append({
                        "id": obj.id,
                        "source": obj.source,
                        "name": obj.name,
                        "target": obj.target,
                        "status": obj.status,
                        "task_id": task_id,
                        "started_at_ns": obj.started_at_ns,
                        "ended_at_ns": obj.ended_at_ns,
                        "metadata": meta,
                    })
            return results

    async def get_statistics(self, session_id: str) -> dict[str, int]:
        async with self.session_factory() as db:  # type: AsyncSession
            evt_count = await db.scalar(
                select(func.count(TraceEventModel.event_id)).where(TraceEventModel.session_id == session_id)
            ) or 0
            req_count = await db.scalar(
                select(func.count(NetworkRequestModel.id)).where(NetworkRequestModel.session_id == session_id)
            ) or 0
            res_count = await db.scalar(
                select(func.count(NetworkResponseModel.id)).join(
                    NetworkRequestModel, NetworkResponseModel.request_id == NetworkRequestModel.id
                ).where(NetworkRequestModel.session_id == session_id)
            ) or 0
            storage_count = await db.scalar(
                select(func.count(StorageOperationModel.id)).where(StorageOperationModel.session_id == session_id)
            ) or 0

            return {
                "total_events": evt_count,
                "network_requests": req_count,
                "network_responses": res_count,
                "storage_operations": storage_count,
            }
