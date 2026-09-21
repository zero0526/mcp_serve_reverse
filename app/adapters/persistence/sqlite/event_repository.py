import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    NetworkRequestModel,
    NetworkResponseModel,
    StorageOperationModel,
    TraceEventModel,
)
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope
from app.infrastructure.config.settings import settings
from app.infrastructure.serialization.json import safe_dumps, safe_loads
from app.ports.event_store import EventStorePort
from app.ports.repositories import EventRepositoryPort


class SQLiteEventRepository(EventStorePort, EventRepositoryPort):
    """Repository phụ trách lưu trữ Event Store và phân rã các thực thể Network / Storage."""

    def __init__(self, session_factory=AsyncSessionLocal, base_sessions_dir: Path | None = None):
        self.session_factory = session_factory
        self.sessions_dir = base_sessions_dir or settings.sessions_dir

    def _append_raw_jsonl(self, session_id: str, raw_line: str) -> None:
        """Ghi raw event stream dạng JSONL để backup và phục vụ rebuild."""
        session_folder = self.sessions_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        raw_file = session_folder / "raw_events.jsonl"
        with open(raw_file, "a", encoding="utf-8") as f:
            f.write(raw_line + "\n")

    async def persist_event(
        self,
        event: EventEnvelope,
        normalized: dict[str, Any],
        raw_json: str | None = None,
    ) -> None:
        payload_str = safe_dumps(event.payload)
        metadata_str = safe_dumps(event.metadata)
        payload_hash = normalized.get("payload_hash")

        # 1. Ghi JSONL stream
        line = raw_json or safe_dumps(event.model_dump())
        self._append_raw_jsonl(event.session_id, line)

        ev_type = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        )
        if ev_type.startswith("EventType."):
            ev_type = ev_type.split(".", 1)[1].lower()

        # 2. Ghi SQLite trace_events
        trace_record = TraceEventModel(
            event_id=event.event_id,
            session_id=event.session_id,
            schema_version=event.schema_version,
            source=event.source,
            event_type=ev_type,
            timestamp_ns=event.timestamp_ns,
            sequence=event.sequence,
            page_id=event.page_id,
            frame_id=event.frame_id,
            execution_id=event.execution_id,
            parent_execution_id=event.parent_execution_id,
            payload_json=payload_str,
            metadata_json=metadata_str,
            payload_hash=payload_hash,
            ingested_at_ns=event.timestamp_ns,
        )

        async with self.session_factory() as db:  # type: AsyncSession
            db.add(trace_record)
            await db.flush()

            # 3. Phân tách và ghi vào bảng thực thể chuyên biệt
            if ev_type == EventType.NETWORK_REQUEST.value:
                payload = event.payload
                url_parsed = normalized.get("url_parsed", {})
                req_id = payload.get("request_id") or event.event_id
                existing_req = (
                    await db.execute(select(NetworkRequestModel).where(NetworkRequestModel.id == req_id))
                ).scalar_one_or_none()

                if existing_req:
                    existing_req.method = payload.get("method", "GET")
                    existing_req.url = payload.get("url", "")
                    existing_req.host = url_parsed.get("host") or payload.get("host")
                    existing_req.path = url_parsed.get("path") or payload.get("path")
                    existing_req.query_json = safe_dumps(url_parsed.get("query") or payload.get("query") or {})
                    existing_req.headers_json = safe_dumps(payload.get("headers", {}))
                    existing_req.body_json = safe_dumps(payload.get("body")) if payload.get("body") else None
                    existing_req.resource_type = payload.get("resource_type")
                    existing_req.status = "captured"
                else:
                    req_record = NetworkRequestModel(
                        id=req_id,
                        session_id=event.session_id,
                        event_id=event.event_id,
                        execution_id=event.execution_id,
                        page_id=event.page_id,
                        frame_id=event.frame_id,
                        method=payload.get("method", "GET"),
                        url=payload.get("url", ""),
                        host=url_parsed.get("host") or payload.get("host"),
                        path=url_parsed.get("path") or payload.get("path"),
                        query_json=safe_dumps(url_parsed.get("query") or payload.get("query") or {}),
                        headers_json=safe_dumps(payload.get("headers", {})),
                        body_json=safe_dumps(payload.get("body")) if payload.get("body") else None,
                        resource_type=payload.get("resource_type"),
                        started_at_ns=event.timestamp_ns,
                        status="captured",
                        metadata_json=metadata_str,
                    )
                    db.add(req_record)

            elif ev_type == EventType.NETWORK_RESPONSE.value:
                payload = event.payload
                req_id = payload.get("request_id") or "unknown_req"

                # Kiểm tra nếu request đã tồn tại thì liên kết, nếu chưa tạo request placeholder
                res_check = await db.execute(select(NetworkRequestModel).where(NetworkRequestModel.id == req_id))
                if not res_check.scalar_one_or_none():
                    placeholder_req = NetworkRequestModel(
                        id=req_id,
                        session_id=event.session_id,
                        event_id=event.event_id,
                        method="UNKNOWN",
                        url=payload.get("url", ""),
                        started_at_ns=event.timestamp_ns,
                        status="placeholder",
                    )
                    db.add(placeholder_req)

                res_record = NetworkResponseModel(
                    id=f"res_{event.event_id}",
                    request_id=req_id,
                    event_id=event.event_id,
                    status_code=payload.get("status_code"),
                    headers_json=safe_dumps(payload.get("headers", {})),
                    body_json=safe_dumps(payload.get("body")) if payload.get("body") else None,
                    received_at_ns=event.timestamp_ns,
                    metadata_json=metadata_str,
                )
                db.add(res_record)

            elif ev_type in [
                EventType.STORAGE_READ.value,
                EventType.STORAGE_WRITE.value,
                EventType.STORAGE_DELETE.value,
                EventType.STORAGE_CLEAR.value,
            ]:
                payload = event.payload
                storage_record = StorageOperationModel(
                    id=f"st_{event.event_id}",
                    session_id=event.session_id,
                    event_id=event.event_id,
                    execution_id=event.execution_id,
                    page_id=event.page_id,
                    frame_id=event.frame_id,
                    storage_type=payload.get("storage_type", "local_storage"),
                    storage_key=payload.get("storage_key", "*all*"),
                    operation=payload.get("operation", "unknown"),
                    value_ref=payload.get("value_preview"),
                    timestamp_ns=event.timestamp_ns,
                    metadata_json=metadata_str,
                )
                db.add(storage_record)

            await db.commit()

    async def batch_persist_events(
        self,
        items: list[tuple[EventEnvelope, dict[str, Any]]],
    ) -> None:
        for event, normalized in items:
            await self.persist_event(event, normalized)

    async def save_trace_event(self, event: EventEnvelope) -> None:
        await self.persist_event(event, {})

    async def save_network_request(self, request_data: dict[str, Any]) -> None:
        pass

    async def save_network_response(self, response_data: dict[str, Any]) -> None:
        pass

    async def save_storage_operation(self, op_data: dict[str, Any]) -> None:
        pass

    async def search_events(
        self,
        session_id: str,
        event_types: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(TraceEventModel).where(TraceEventModel.session_id == session_id)
            if event_types:
                stmt = stmt.where(TraceEventModel.event_type.in_(event_types))
            stmt = stmt.order_by(TraceEventModel.timestamp_ns.asc(), TraceEventModel.sequence.asc())
            stmt = stmt.limit(limit).offset(offset)

            res = await db.execute(stmt)
            records = res.scalars().all()

            results = []
            for r in records:
                results.append({
                    "event_id": r.event_id,
                    "session_id": r.session_id,
                    "event_type": r.event_type,
                    "timestamp_ns": r.timestamp_ns,
                    "sequence": r.sequence,
                    "payload": safe_loads(r.payload_json),
                    "metadata": safe_loads(r.metadata_json),
                })
            return results
