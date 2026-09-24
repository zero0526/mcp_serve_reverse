"""Routes xử lý API Graph Studio (Query graph, Update alias, Delete node)."""

from sqlalchemy import select, update
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.adapters.persistence.sqlite.models import GraphNodeModel
from app.infrastructure.serialization.json import safe_dumps, safe_loads
from playground.backend.dependencies import get_container


async def get_graph_endpoint(request: Request) -> JSONResponse:
    """GET /api/graph/{session_id}: Lấy toàn bộ nodes và edges của session."""
    session_id = request.path_params["session_id"]
    container = await get_container()

    raw_nodes = await container.graph_repository.get_nodes(session_id)
    raw_edges = await container.graph_repository.get_edges(session_id)

    formatted_nodes = []
    for n in raw_nodes:
        props = n.properties or {}
        alias = props.get("alias") or (n.label if n.label and n.label != n.id else None)
        node_type_str = n.node_type.value if hasattr(n.node_type, "value") else str(n.node_type)

        formatted_nodes.append({
            "id": n.id,
            "session_id": n.session_id,
            "node_type": node_type_str,
            "label": n.label or n.id,
            "alias": alias,
            "entity_id": n.entity_id,
            "properties": props,
            "created_at_ns": n.created_at_ns,
        })

    formatted_edges = []
    for e in raw_edges:
        rel_str = e.relation_type.value if hasattr(e.relation_type, "value") else str(e.relation_type)
        formatted_edges.append({
            "id": e.id,
            "session_id": e.session_id,
            "source_id": e.source_id,
            "target_id": e.target_id,
            "relation_type": rel_str,
            "confidence": e.confidence,
            "provenance_status": e.provenance_status,
            "properties": e.properties or {},
        })

    return JSONResponse({
        "nodes": formatted_nodes,
        "edges": formatted_edges,
    })


async def update_node_alias_endpoint(request: Request) -> JSONResponse:
    """PATCH /api/graph/{session_id}/nodes/{node_id}/alias: Gán tên gợi nhớ (alias) cho node."""
    session_id = request.path_params["session_id"]
    node_id = request.path_params["node_id"]

    try:
        body = await request.json()
    except Exception:
        body = {}

    alias = body.get("alias", "").strip()
    container = await get_container()

    async with container.session_factory() as db:
        stmt = select(GraphNodeModel).where(
            GraphNodeModel.id == node_id,
            GraphNodeModel.session_id == session_id,
        )
        res = await db.execute(stmt)
        node_obj = res.scalar_one_or_none()

        if not node_obj:
            return JSONResponse({"detail": f"Node '{node_id}' not found."}, status_code=404)

        props = safe_loads(node_obj.properties_json) if node_obj.properties_json else {}
        props["alias"] = alias
        node_obj.label = alias
        node_obj.properties_json = safe_dumps(props)

        await db.commit()

    return JSONResponse({"success": True, "node_id": node_id, "alias": alias})


async def delete_node_endpoint(request: Request) -> JSONResponse:
    """DELETE /api/graph/{session_id}/nodes/{node_id}: Xóa node và cascade các cạnh liên quan."""
    session_id = request.path_params["session_id"]
    node_id = request.path_params["node_id"]
    container = await get_container()

    await container.graph_repository.delete_nodes([node_id])

    return JSONResponse({
        "success": True,
        "deleted_node_id": node_id,
        "session_id": session_id,
    })
