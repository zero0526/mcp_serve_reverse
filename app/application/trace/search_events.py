from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import TraceEventModel
from app.infrastructure.serialization.json import safe_loads


class SearchTraceEventsUseCase:
    """Use case tìm kiếm sự kiện vết (Trace Events) có bộ lọc và phân trang."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    async def execute(
        self,
        session_id: str,
        event_types: list[str] | None = None,
        page_id: str | None = None,
        start_ns: int | None = None,
        end_ns: int | None = None,
        keyword: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:  # type: AsyncSession
            conditions = [TraceEventModel.session_id == session_id]

            if event_types:
                conditions.append(TraceEventModel.event_type.in_(event_types))
            if page_id:
                conditions.append(TraceEventModel.page_id == page_id)
            if start_ns is not None:
                conditions.append(TraceEventModel.timestamp_ns >= start_ns)
            if end_ns is not None:
                conditions.append(TraceEventModel.timestamp_ns <= end_ns)
            if keyword:
                conditions.append(TraceEventModel.payload_json.like(f"%{keyword}%"))

            # Đếm tổng số bản ghi
            count_stmt = select(func.count(TraceEventModel.event_id)).where(*conditions)
            total_count = (await db.execute(count_stmt)).scalar() or 0

            # Lấy dữ liệu phân trang
            stmt = (
                select(TraceEventModel)
                .where(*conditions)
                .order_by(TraceEventModel.timestamp_ns.asc(), TraceEventModel.sequence.asc())
                .offset(offset)
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()

            events = [
                {
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "timestamp_ns": r.timestamp_ns,
                    "sequence": r.sequence,
                    "page_id": r.page_id,
                    "frame_id": r.frame_id,
                    "payload": safe_loads(r.payload_json) if r.payload_json else {},
                    "metadata": safe_loads(r.metadata_json) if r.metadata_json else {},
                }
                for r in rows
            ]

            return {
                "session_id": session_id,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "events": events,
            }
