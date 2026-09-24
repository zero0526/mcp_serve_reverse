from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.graph.compact_graph import CompactGraphUseCase
from app.application.graph.query_graph_nodes import (
    GetGraphNeighborsUseCase,
    GetGraphNodeUseCase,
    GetGraphStatisticsUseCase,
)
from app.application.graph.rebuild_graph import RebuildGraphUseCase
from app.interfaces.mcp.schemas.responses import create_mcp_response

_graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
_node_uc = GetGraphNodeUseCase(graph_repo=_graph_repo)
_neighbors_uc = GetGraphNeighborsUseCase(graph_repo=_graph_repo)
_stats_uc = GetGraphStatisticsUseCase(graph_repo=_graph_repo)
_rebuild_uc = RebuildGraphUseCase(graph_repository=_graph_repo, session_factory=AsyncSessionLocal)
_compact_uc = CompactGraphUseCase(graph_repository=_graph_repo, session_factory=AsyncSessionLocal)


async def get_graph_node_tool(
    session_id: str,
    node_id: str,
    include_evidence: bool = True,
) -> dict[str, Any]:
    """MCP Tool: Lấy chi tiết thông tin của một GraphNode và các bằng chứng (evidence) liên kết."""
    res = await _node_uc.execute(
        session_id=session_id,
        node_id=node_id,
        include_evidence=include_evidence,
    )
    if not res:
        return create_mcp_response(
            status="NOT_FOUND",
            data={},
            session_id=session_id,
            warnings=[f"Không tìm thấy node '{node_id}' trong session '{session_id}'."],
            source="graph_query",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        source="graph_query",
    )


async def get_graph_neighbors_tool(
    session_id: str,
    node_id: str,
    direction: str = "both",
    edge_types: list[str] | None = None,
    min_confidence: float = 0.8,
    limit: int = 100,
) -> dict[str, Any]:
    """MCP Tool: Truy vấn các node lân cận (1-hop neighbors) theo hướng in/out/both."""
    safe_limit = max(1, min(limit, 500))
    res = await _neighbors_uc.execute(
        session_id=session_id,
        node_id=node_id,
        direction=direction.lower(),
        edge_types=edge_types,
        min_confidence=min_confidence,
        limit=safe_limit,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res["total_count"],
        source="graph_query",
    )


async def get_graph_statistics_tool(
    session_id: str,
    include_edge_distribution: bool = True,
    include_orphans: bool = True,
) -> dict[str, Any]:
    """MCP Tool: Lấy số liệu thống kê chất lượng đồ thị và phân bố quan hệ."""
    res = await _stats_uc.execute(
        session_id=session_id,
        include_edge_distribution=include_edge_distribution,
        include_orphans=include_orphans,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        source="graph_query",
    )


async def rebuild_graph_tool(session_id: str) -> dict[str, Any]:
    """MCP Tool: Xóa bỏ toàn bộ graph cũ của session và tái thiết lập lại từ SQLite raw trace events."""
    res = await _rebuild_uc.execute(session_id=session_id)
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res.get("nodes_count", 0),
        source="graph_rebuild",
    )


async def compact_graph_tool(
    session_id: str,
    prune_static: bool = True,
    prune_internals: bool = True,
    prune_isolated: bool = True,
    keep_node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """MCP Tool: Tinh gọn và cắt tỉa đồ thị: loại bỏ file tĩnh (.css, .png), framework internals và node cô lập."""
    res = await _compact_uc.execute(
        session_id=session_id,
        options={
            "prune_static": prune_static,
            "prune_internals": prune_internals,
            "prune_isolated": prune_isolated,
            "keep_node_ids": keep_node_ids or [],
        },
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res.get("remaining_nodes_count", 0),
        source="graph_compaction",
    )
