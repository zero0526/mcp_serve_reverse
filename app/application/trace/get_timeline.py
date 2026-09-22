from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import TraceEventModel
from app.infrastructure.serialization.json import safe_loads


class GetTraceTimelineUseCase:
    """Use case lấy dòng thời gian sự kiện (Timeline) đã chuẩn hóa cho LLM."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    async def execute(
        self,
        session_id: str,
        event_types: list[str] | None = None,
        start_ns: int | None = None,
        end_ns: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:  # type: AsyncSession
            conditions = [TraceEventModel.session_id == session_id]
            if event_types:
                conditions.append(TraceEventModel.event_type.in_(event_types))
            if start_ns is not None:
                conditions.append(TraceEventModel.timestamp_ns >= start_ns)
            if end_ns is not None:
                conditions.append(TraceEventModel.timestamp_ns <= end_ns)

            stmt = (
                select(TraceEventModel)
                .where(*conditions)
                .order_by(TraceEventModel.timestamp_ns.asc(), TraceEventModel.sequence.asc())
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()

            timeline = []
            for r in rows:
                payload = safe_loads(r.payload_json) if r.payload_json else {}
                summary = r.event_type
                if r.event_type == "network_request":
                    summary = f"{payload.get('method', 'GET')} {payload.get('url', '')}"
                elif r.event_type == "network_response":
                    summary = f"Status {payload.get('status_code', 200)} for {payload.get('url', '')}"
                elif r.event_type in ["storage_read", "storage_write"]:
                    summary = f"{payload.get('storage_type')}.{payload.get('storage_key')}"
                elif r.event_type == "crypto_operation":
                    summary = f"Crypto {payload.get('operation')} ({payload.get('algorithm')})"
                elif r.event_type == "response_field_read":
                    summary = f"Read field '{payload.get('field')}'"

                timeline.append({
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "timestamp_ns": r.timestamp_ns,
                    "sequence": r.sequence,
                    "summary": summary,
                })

            return {
                "session_id": session_id,
                "ordering": "timestamp_then_sequence",
                "timeline": timeline,
                "count": len(timeline),
            }
