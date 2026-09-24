from collections import Counter
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import SessionLogModel
from app.domain.task.retro_entities import LogType, SessionLog
from app.infrastructure.serialization.json import safe_dumps, safe_loads
from app.ports.session_log_repository import SessionLogRepositoryPort


class SQLiteSessionLogRepository(SessionLogRepositoryPort):
    """Triển khai lưu trữ nhật ký hồi cứu và tiến hóa MCP tools trong SQLite."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    def _to_entity(self, model: SessionLogModel) -> SessionLog:
        missing_tools = safe_loads(model.missing_tools_json) if model.missing_tools_json else []
        suggested_tools = safe_loads(model.suggested_tools_json) if model.suggested_tools_json else []
        bottlenecks = safe_loads(model.bottlenecks_json) if model.bottlenecks_json else []
        metadata = safe_loads(model.metadata_json) if model.metadata_json else {}

        return SessionLog(
            id=model.id,
            task_id=model.task_id,
            session_id=model.session_id,
            log_type=LogType(model.log_type) if model.log_type in LogType._value2member_map_ else LogType.RETROSPECTIVE,
            agent_evaluation=model.agent_evaluation,
            missing_tools=missing_tools,
            suggested_tools=suggested_tools,
            bottlenecks=bottlenecks,
            efficiency_rating=model.efficiency_rating,
            created_at_ns=model.created_at_ns,
            metadata=metadata,
        )

    async def create(
        self,
        log_id: str,
        task_id: str,
        agent_evaluation: str,
        session_id: str | None = None,
        log_type: LogType | str = LogType.RETROSPECTIVE,
        missing_tools: list[str] | None = None,
        suggested_tools: list[dict[str, Any]] | None = None,
        bottlenecks: list[str] | None = None,
        efficiency_rating: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLog:
        now_ns = time.time_ns()
        type_val = log_type.value if isinstance(log_type, LogType) else str(log_type)

        model = SessionLogModel(
            id=log_id,
            task_id=task_id,
            session_id=session_id,
            log_type=type_val,
            agent_evaluation=agent_evaluation,
            missing_tools_json=safe_dumps(missing_tools or []),
            suggested_tools_json=safe_dumps(suggested_tools or []),
            bottlenecks_json=safe_dumps(bottlenecks or []),
            efficiency_rating=efficiency_rating,
            created_at_ns=now_ns,
            metadata_json=safe_dumps(metadata or {}),
        )

        async with self.session_factory() as db:  # type: AsyncSession
            db.add(model)
            await db.commit()
            return self._to_entity(model)

    async def list_by_task_id(
        self,
        task_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SessionLog]:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = (
                select(SessionLogModel)
                .where(SessionLogModel.task_id == task_id)
                .order_by(SessionLogModel.created_at_ns.desc())
                .limit(limit)
                .offset(offset)
            )
            res = await db.execute(stmt)
            records = res.scalars().all()
            return [self._to_entity(r) for r in records]

    async def list_all(
        self,
        log_type: LogType | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionLog]:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = (
                select(SessionLogModel)
                .order_by(SessionLogModel.created_at_ns.desc())
                .limit(limit)
                .offset(offset)
            )
            if log_type:
                type_val = log_type.value if isinstance(log_type, LogType) else str(log_type)
                stmt = stmt.where(SessionLogModel.log_type == type_val)

            res = await db.execute(stmt)
            records = res.scalars().all()
            return [self._to_entity(r) for r in records]

    async def get_evolution_summary(self, task_id: str | None = None) -> dict[str, Any]:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(SessionLogModel)
            if task_id:
                stmt = stmt.where(SessionLogModel.task_id == task_id)

            res = await db.execute(stmt)
            records = res.scalars().all()

        total_retrospectives = len(records)
        if total_retrospectives == 0:
            return {
                "total_retrospectives": 0,
                "average_efficiency_rating": 0.0,
                "top_missing_tools": [],
                "recent_proposals": [],
                "common_bottlenecks": [],
            }

        missing_counter = Counter()
        bottlenecks_counter = Counter()
        proposals: list[dict[str, Any]] = []
        total_rating = 0

        for r in records:
            total_rating += r.efficiency_rating
            miss = safe_loads(r.missing_tools_json) if r.missing_tools_json else []
            for m in miss:
                missing_counter[m] += 1

            sugg = safe_loads(r.suggested_tools_json) if r.suggested_tools_json else []
            for s in sugg:
                if isinstance(s, dict):
                    proposals.append({
                        "task_id": r.task_id,
                        "created_at_ns": r.created_at_ns,
                        **s,
                    })

            bn = safe_loads(r.bottlenecks_json) if r.bottlenecks_json else []
            for b in bn:
                bottlenecks_counter[b] += 1

        top_missing = [{"tool": k, "frequency": v} for k, v in missing_counter.most_common(10)]
        common_bn = [{"bottleneck": k, "frequency": v} for k, v in bottlenecks_counter.most_common(10)]

        return {
            "total_retrospectives": total_retrospectives,
            "average_efficiency_rating": round(total_rating / total_retrospectives, 2),
            "top_missing_tools": top_missing,
            "recent_proposals": proposals[-10:],
            "common_bottlenecks": common_bn,
        }
