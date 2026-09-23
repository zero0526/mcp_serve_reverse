"""Session MCP Resource: session://{session_id}

Provides metadata, statistics, top endpoints, and storage summary for a given session.
Guarded by TruncationGuard and RedactionEngine.
"""

import json
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    GraphEdgeModel,
    GraphNodeModel,
    NetworkRequestModel,
    NetworkResponseModel,
    SessionModel,
    StorageOperationModel,
    TraceEventModel,
)
from app.infrastructure.serialization.json import safe_loads
from app.interfaces.mcp.context import default_truncation_guard


async def get_session_resource(
    session_id: str,
    session_factory=AsyncSessionLocal,
    redaction_mode: str = "strict",
) -> str:
    """Đọc dữ liệu resource session://{session_id} và trả về chuỗi JSON chuẩn hóa."""
    async with session_factory() as db:  # type: AsyncSession
        # 1. Lấy thông tin session
        sess_stmt = select(SessionModel).where(SessionModel.id == session_id)
        session_row = (await db.execute(sess_stmt)).scalars().first()

        if not session_row:
            error_payload = {
                "uri": f"session://{session_id}",
                "error": "SESSION_NOT_FOUND",
                "message": f"Session '{session_id}' does not exist in event store.",
                "metadata": {"truncated": False, "warnings": []},
            }
            return json.dumps(error_payload, indent=2, ensure_ascii=False)

        # 2. Thống kê số lượng bản ghi
        req_count = (
            await db.execute(
                select(func.count(NetworkRequestModel.id)).where(NetworkRequestModel.session_id == session_id)
            )
        ).scalar() or 0

        res_count = (
            await db.execute(
                select(func.count(NetworkResponseModel.id))
                .join(NetworkRequestModel, NetworkResponseModel.request_id == NetworkRequestModel.id)
                .where(NetworkRequestModel.session_id == session_id)
            )
        ).scalar() or 0

        stor_count = (
            await db.execute(
                select(func.count(StorageOperationModel.id)).where(StorageOperationModel.session_id == session_id)
            )
        ).scalar() or 0

        trace_count = (
            await db.execute(
                select(func.count(TraceEventModel.event_id)).where(TraceEventModel.session_id == session_id)
            )
        ).scalar() or 0

        node_count = (
            await db.execute(
                select(func.count(GraphNodeModel.id)).where(GraphNodeModel.session_id == session_id)
            )
        ).scalar() or 0

        edge_count = (
            await db.execute(
                select(func.count(GraphEdgeModel.id)).where(GraphEdgeModel.session_id == session_id)
            )
        ).scalar() or 0

        # 3. Lấy danh sách tóm tắt endpoints (giới hạn 30 requests gần nhất)
        req_stmt = (
            select(NetworkRequestModel)
            .where(NetworkRequestModel.session_id == session_id)
            .order_by(NetworkRequestModel.started_at_ns.asc())
            .limit(30)
        )
        recent_reqs = (await db.execute(req_stmt)).scalars().all()

        endpoints_summary = []
        for r in recent_reqs:
            endpoints_summary.append({
                "request_id": r.id,
                "method": r.method,
                "url": r.url,
                "resource_type": r.resource_type,
                "started_at_ns": r.started_at_ns,
            })

        # 4. Lấy danh sách các unique storage keys
        stor_keys_stmt = (
            select(StorageOperationModel.storage_key)
            .where(StorageOperationModel.session_id == session_id)
            .distinct()
            .limit(50)
        )
        storage_keys = [k for k in (await db.execute(stor_keys_stmt)).scalars().all() if k]

        session_meta = safe_loads(session_row.metadata_json) if session_row.metadata_json else {}

        raw_data: dict[str, Any] = {
            "uri": f"session://{session_id}",
            "session": {
                "id": session_row.id,
                "name": session_row.name,
                "source": session_row.source,
                "status": session_row.status,
                "target": session_row.target,
                "started_at_ns": session_row.started_at_ns,
                "ended_at_ns": session_row.ended_at_ns,
                "created_at_ns": session_row.created_at_ns,
                "metadata": session_meta,
            },
            "summary": {
                "counts": {
                    "network_requests": req_count,
                    "network_responses": res_count,
                    "storage_operations": stor_count,
                    "trace_events": trace_count,
                    "graph_nodes": node_count,
                    "graph_edges": edge_count,
                },
                "endpoints": endpoints_summary,
                "storage_keys": storage_keys,
            },
        }

    # 5. Áp dụng bảo vệ TruncationGuard & Redaction
    guarded_data, is_truncated, warnings = default_truncation_guard.process_resource_data(
        raw_data, redaction_mode=redaction_mode
    )
    guarded_data["metadata"] = {
        "truncated": is_truncated,
        "warnings": warnings,
    }

    return json.dumps(guarded_data, indent=2, ensure_ascii=False)
