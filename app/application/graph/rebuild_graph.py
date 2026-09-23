import time
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.graph.graph_projector import GraphProjector, graph_projector
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.models import (
    NetworkRequestModel,
    NetworkResponseModel,
    StorageOperationModel,
    TraceEventModel,
)
from app.ports.graph_repository import GraphRepositoryPort


class RebuildGraphUseCase:
    """Use case xóa bỏ toàn bộ graph cũ của một session và tái thiết lập lại từ trace events gốc."""

    def __init__(
        self,
        graph_repository: GraphRepositoryPort | None = None,
        projector: GraphProjector = graph_projector,
        session_factory=AsyncSessionLocal,
    ):
        self.graph_repo = graph_repository or SQLiteGraphRepository(session_factory)
        self.projector = projector
        self.session_factory = session_factory

    async def execute(self, session_id: str) -> dict[str, Any]:
        start_ns = time.time_ns()

        # 1. Xóa sạch toàn bộ graph hiện tại của session
        await self.graph_repo.delete_session_graph(session_id)

        # 2. Đọc lại toàn bộ dữ liệu gốc từ SQLite
        async with self.session_factory() as db:  # type: AsyncSession
            # Requests
            req_stmt = (
                select(NetworkRequestModel)
                .where(NetworkRequestModel.session_id == session_id)
                .order_by(NetworkRequestModel.started_at_ns.asc())
            )
            req_rows = (await db.execute(req_stmt)).scalars().all()
            requests = [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "method": r.method,
                    "url": r.url,
                    "host": r.host,
                    "path": r.path,
                    "query_json": r.query_json,
                    "headers_json": r.headers_json,
                    "body_json": r.body_json,
                    "started_at_ns": r.started_at_ns,
                }
                for r in req_rows
            ]

            # Responses
            res_stmt = (
                select(NetworkResponseModel)
                .join(
                    NetworkRequestModel,
                    NetworkResponseModel.request_id == NetworkRequestModel.id,
                )
                .where(NetworkRequestModel.session_id == session_id)
            )
            res_rows = (await db.execute(res_stmt)).scalars().all()
            responses = [
                {
                    "id": r.id,
                    "request_id": r.request_id,
                    "status_code": r.status_code,
                    "headers_json": r.headers_json,
                    "body_json": r.body_json,
                    "received_at_ns": r.received_at_ns,
                }
                for r in res_rows
            ]

            # Storage Operations
            storage_stmt = (
                select(StorageOperationModel)
                .where(StorageOperationModel.session_id == session_id)
                .order_by(StorageOperationModel.timestamp_ns.asc())
            )
            storage_rows = (await db.execute(storage_stmt)).scalars().all()
            storage_ops = [
                {
                    "id": r.id,
                    "session_id": r.session_id,
                    "event_id": r.event_id,
                    "storage_type": r.storage_type,
                    "storage_key": r.storage_key,
                    "operation": r.operation,
                    "value_ref": r.value_ref,
                    "timestamp_ns": r.timestamp_ns,
                }
                for r in storage_rows
            ]

            # Trace Events
            event_stmt = (
                select(TraceEventModel)
                .where(TraceEventModel.session_id == session_id)
                .order_by(TraceEventModel.timestamp_ns.asc())
            )
            event_rows = (await db.execute(event_stmt)).scalars().all()
            trace_events = [
                {
                    "event_id": r.event_id,
                    "event_type": r.event_type,
                    "timestamp_ns": r.timestamp_ns,
                    "payload_json": r.payload_json,
                    "metadata_json": r.metadata_json,
                }
                for r in event_rows
            ]

        # 3. Tái chiếu đồ thị sử dụng projector với các luật cập nhật mới nhất
        nodes, edges = self.projector.project(
            session_id=session_id,
            requests=requests,
            responses=responses,
            storage_ops=storage_ops,
            trace_events=trace_events,
        )

        # 4. Lưu lại toàn bộ kết quả vào kho đồ thị
        await self.graph_repo.save_nodes(nodes)
        await self.graph_repo.save_edges(edges)

        duration_ms = (time.time_ns() - start_ns) / 1_000_000

        return {
            "session_id": session_id,
            "status": "rebuilt",
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "requests_count": len(requests),
            "storage_ops_count": len(storage_ops),
            "duration_ms": round(duration_ms, 2),
        }
