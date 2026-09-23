"""Lineage MCP Resource: lineage://{session_id}/{node_id}

Provides the origin provenance tree, upstream dependencies, and downstream usage for a graph node.
Guarded by TruncationGuard and RedactionEngine.
"""

import json
from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.lineage.trace_lineage import TraceLineageUseCase
from app.interfaces.mcp.context import default_truncation_guard


async def get_lineage_resource(
    session_id: str,
    node_id: str,
    session_factory=AsyncSessionLocal,
    redaction_mode: str = "strict",
) -> str:
    """Đọc dữ liệu resource lineage://{session_id}/{node_id} và trả về chuỗi JSON chuẩn hóa."""
    graph_repo = SQLiteGraphRepository(session_factory=session_factory)
    trace_uc = TraceLineageUseCase(graph_repository=graph_repo)

    # 1. Tìm node mục tiêu
    target_node = await graph_repo.get_node(node_id)
    resolved_node_id = node_id
    if not target_node:
        # Thử tìm theo node_req_{node_id} hoặc entity_id
        nodes = await graph_repo.get_nodes(session_id)
        for n in nodes:
            if n.entity_id == node_id or n.id == f"node_req_{node_id}":
                target_node = n
                resolved_node_id = n.id
                break

    if not target_node:
        error_payload = {
            "uri": f"lineage://{session_id}/{node_id}",
            "error": "NODE_NOT_FOUND",
            "message": f"Graph node '{node_id}' not found in session '{session_id}'.",
            "metadata": {"truncated": False, "warnings": []},
        }
        return json.dumps(error_payload, indent=2, ensure_ascii=False)

    # 2. Truy vết ngược tìm nguồn gốc (Upstream Origin)
    upstream_path = await trace_uc.trace_backward(
        session_id=session_id,
        target_node_id=resolved_node_id,
    )

    upstream_data = None
    if upstream_path:
        steps_summary = [
            {
                "step_number": s.step_number,
                "from_node_id": s.from_node_id,
                "to_node_id": s.to_node_id,
                "relation": s.relation,
                "action": s.action_description,
                "confidence": s.confidence,
                "evidence": s.evidence_refs,
            }
            for s in upstream_path.steps
        ]
        upstream_data = {
            "status": upstream_path.status,
            "overall_confidence": upstream_path.overall_confidence,
            "origin_node_id": upstream_path.origin_node_id,
            "origin_type": upstream_path.origin_type,
            "origin_key": upstream_path.origin_key,
            "target_param": upstream_path.target_param,
            "steps": steps_summary,
        }

    # 3. Truy vết xuôi tìm tác động (Downstream Usage)
    downstream_paths = await trace_uc.trace_forward(
        session_id=session_id,
        origin_node_id=resolved_node_id,
    )
    downstream_summary = [
        {
            "target_node_id": p.target_node_id,
            "target_param": p.target_param,
            "confidence": p.overall_confidence,
            "status": p.status,
        }
        for p in downstream_paths
    ]

    raw_data: dict[str, Any] = {
        "uri": f"lineage://{session_id}/{node_id}",
        "target_node": {
            "id": target_node.id,
            "label": target_node.label,
            "node_type": target_node.node_type,
            "entity_id": target_node.entity_id,
            "properties": target_node.properties,
        },
        "upstream_lineage": upstream_data,
        "downstream_usage": downstream_summary,
    }

    # 4. Áp dụng bảo vệ TruncationGuard & Redaction
    guarded_data, is_truncated, warnings = default_truncation_guard.process_resource_data(
        raw_data, redaction_mode=redaction_mode
    )
    guarded_data["metadata"] = {
        "truncated": is_truncated,
        "warnings": warnings,
    }

    return json.dumps(guarded_data, indent=2, ensure_ascii=False)
