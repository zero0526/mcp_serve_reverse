"""Request MCP Resource: request://{session_id}/{request_id}

Provides detailed request, response, and lineage summary for a specific HTTP transaction.
Guarded by TruncationGuard and RedactionEngine.
"""

import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    GraphEdgeModel,
    NetworkRequestModel,
    NetworkResponseModel,
    TraceEventModel,
)
from app.infrastructure.serialization.json import safe_loads
from app.interfaces.mcp.context import default_truncation_guard


async def get_request_resource(
    session_id: str,
    request_id: str,
    session_factory=AsyncSessionLocal,
    redaction_mode: str = "strict",
) -> str:
    """Đọc dữ liệu resource request://{session_id}/{request_id} và trả về chuỗi JSON chuẩn hóa."""
    async with session_factory() as db:  # type: AsyncSession
        # 1. Tìm NetworkRequestModel
        req_stmt = select(NetworkRequestModel).where(
            NetworkRequestModel.session_id == session_id,
            (NetworkRequestModel.id == request_id) | (NetworkRequestModel.id.like(f"%{request_id}%")),
        )
        req = (await db.execute(req_stmt)).scalars().first()

        if not req:
            error_payload = {
                "uri": f"request://{session_id}/{request_id}",
                "error": "REQUEST_NOT_FOUND",
                "message": f"Request '{request_id}' not found in session '{session_id}'.",
                "metadata": {"truncated": False, "warnings": []},
            }
            return json.dumps(error_payload, indent=2, ensure_ascii=False)

        # 2. Tìm NetworkResponseModel
        res_stmt = select(NetworkResponseModel).where(
            NetworkResponseModel.request_id == req.id
        )
        res = (await db.execute(res_stmt)).scalars().first()

        # 3. Tìm các cạnh Graph liên quan để suy luận Lineage Summary
        req_node_id = f"node_req_{req.id}"
        edge_stmt = select(GraphEdgeModel).where(
            (GraphEdgeModel.target_id == req_node_id) | (GraphEdgeModel.target_id == req.id)
        )
        edges = (await db.execute(edge_stmt)).scalars().all()

        dependencies = []
        for e in edges:
            e_props = safe_loads(e.properties_json) if e.properties_json else {}
            dependencies.append({
                "source_node_id": e.source_id,
                "relation": e.relation_type,
                "confidence": e.confidence,
                "key": e_props.get("storage_key") or e_props.get("path") or e_props.get("param"),
            })

        # 4. Tìm hàm JavaScript kích hoạt (Trigger Function) nếu có trong TraceEvent
        trigger_func = None
        trace_stmt = select(TraceEventModel).where(
            TraceEventModel.session_id == session_id,
            TraceEventModel.event_type.in_(["FUNCTION_EXECUTION", "NETWORK_REQUEST"]),
            TraceEventModel.payload_json.like(f"%{req.id}%"),
        ).limit(5)
        traces = (await db.execute(trace_stmt)).scalars().all()

        for t in traces:
            p = safe_loads(t.payload_json) if t.payload_json else {}
            if "function_name" in p:
                trigger_func = {
                    "function_name": p.get("function_name"),
                    "execution_id": p.get("execution_id"),
                    "source_location": p.get("source_location"),
                }
                break

        # Chuẩn bị dữ liệu thô
        req_headers = safe_loads(req.headers_json) if req.headers_json else {}
        req_query = safe_loads(req.query_json) if req.query_json else {}
        req_body = safe_loads(req.body_json) if req.body_json else None

        res_info = None
        if res:
            res_headers = safe_loads(res.headers_json) if res.headers_json else {}
            res_body = safe_loads(res.body_json) if res.body_json else None
            timing_ms = (
                round((res.received_at_ns - req.started_at_ns) / 1_000_000, 2)
                if (res.received_at_ns and req.started_at_ns)
                else None
            )
            res_info = {
                "status_code": res.status_code,
                "headers": res_headers,
                "body": res_body,
                "timing_ms": timing_ms,
            }

        raw_data: dict[str, Any] = {
            "uri": f"request://{session_id}/{req.id}",
            "request": {
                "id": req.id,
                "method": req.method,
                "url": req.url,
                "host": req.host,
                "path": req.path,
                "resource_type": req.resource_type,
                "started_at_ns": req.started_at_ns,
                "query": req_query,
                "headers": req_headers,
                "body": req_body,
            },
            "response": res_info,
            "lineage_summary": {
                "dependencies": dependencies,
                "triggered_by": trigger_func,
                "has_dependencies": len(dependencies) > 0,
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
