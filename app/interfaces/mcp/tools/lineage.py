from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.lineage.compare_lineage import CompareLineageUseCase
from app.application.lineage.differential_analysis import DifferentialAnalysisUseCase
from app.application.lineage.explain_path import ExplainLineagePathUseCase
from app.application.lineage.find_transformations import FindTransformationsUseCase
from app.application.lineage.trace_downstream import TraceDownstreamUseCase
from app.application.lineage.trace_origin import TraceOriginUseCase
from app.interfaces.mcp.schemas.responses import create_mcp_response

_graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
_origin_uc = TraceOriginUseCase(graph_repo=_graph_repo)
_downstream_uc = TraceDownstreamUseCase(graph_repo=_graph_repo)
_explain_uc = ExplainLineagePathUseCase(graph_repo=_graph_repo)
_compare_uc = CompareLineageUseCase(graph_repo=_graph_repo)
_transform_uc = FindTransformationsUseCase(graph_repository=_graph_repo)
_differential_uc = DifferentialAnalysisUseCase(session_factory=AsyncSessionLocal)


async def trace_origin_tool(
    session_id: str,
    target_node_id: str,
    max_depth: int = 10,
    max_paths: int = 20,
    min_confidence: float = 0.8,
    include_heuristics: bool = False,
) -> dict[str, Any]:
    """MCP Tool: Truy ngược nguồn gốc dữ liệu của một node hoặc tham số từ đồ thị."""
    safe_depth = max(1, min(max_depth, 50))
    safe_paths = max(1, min(max_paths, 100))
    res = await _origin_uc.execute(
        session_id=session_id,
        target_node_id=target_node_id,
        max_depth=safe_depth,
        max_paths=safe_paths,
        min_confidence=min_confidence,
        include_heuristics=include_heuristics,
    )
    return create_mcp_response(
        status="COMPLETED" if not res.get("truncated") else "PARTIAL",
        data=res,
        session_id=session_id,
        result_count=res.get("paths_returned", 0),
        truncated=res.get("truncated", False),
        source="lineage_analysis",
    )


async def trace_downstream_tool(
    session_id: str,
    source_node_id: str,
    max_depth: int = 10,
    max_nodes: int = 200,
    min_confidence: float = 0.8,
) -> dict[str, Any]:
    """MCP Tool: Tìm kiếm tất cả các nơi dữ liệu được sử dụng xuôi dòng trong workflow."""
    safe_depth = max(1, min(max_depth, 50))
    safe_nodes = max(1, min(max_nodes, 500))
    res = await _downstream_uc.execute(
        session_id=session_id,
        source_node_id=source_node_id,
        max_depth=safe_depth,
        max_nodes=safe_nodes,
        min_confidence=min_confidence,
    )
    return create_mcp_response(
        status="COMPLETED" if not res.get("truncated") else "PARTIAL",
        data=res,
        session_id=session_id,
        result_count=len(res.get("usages", [])),
        truncated=res.get("truncated", False),
        source="lineage_analysis",
    )


async def explain_lineage_path_tool(
    session_id: str,
    target_node_id: str,
    path_id: str | None = None,
) -> dict[str, Any]:
    """MCP Tool: Giải thích chuỗi chứng minh nguồn gốc dữ liệu theo dạng con người/LLM dễ hiểu."""
    res = await _explain_uc.execute(
        session_id=session_id,
        target_node_id=target_node_id,
        path_id=path_id,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        warnings=res.get("unknowns"),
        source="lineage_analysis",
    )


async def compare_lineage_tool(
    left_session_id: str,
    left_node_id: str,
    right_session_id: str,
    right_node_id: str,
    comparison_mode: str = "structure",
) -> dict[str, Any]:
    """MCP Tool: So sánh hai đường dẫn Lineage hoặc sự khác biệt giữa hai lần chạy."""
    res = await _compare_uc.execute(
        left_session_id=left_session_id,
        left_node_id=left_node_id,
        right_session_id=right_session_id,
        right_node_id=right_node_id,
        comparison_mode=comparison_mode,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=left_session_id,
        source="lineage_analysis",
    )


async def find_transformations_tool(
    session_id: str,
    source: dict[str, Any] | str | None = None,
    target: dict[str, Any] | str | None = None,
    transformation_types: list[str] | None = None,
    direction: str = "both",
    max_depth: int = 10,
    include_arguments: bool = True,
) -> dict[str, Any]:
    """MCP Tool: Phân tích chuỗi các hàm biến đổi dữ liệu liên tiếp (encode, hash, encrypt, serialize)."""
    safe_depth = max(1, min(max_depth, 50))
    res = await _transform_uc.execute(
        session_id=session_id,
        source=source,
        target=target,
        transformation_types=transformation_types,
        direction=direction,
        max_depth=safe_depth,
        include_arguments=include_arguments,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res.get("count", 0),
        source="lineage_transformations",
    )


async def differential_analysis_tool(task_id: str) -> dict[str, Any]:
    """MCP Tool: So sánh vi phân đa phiên thuộc cùng Task ID để tự động phân loại tham số:
    CONSTANT, TIMESTAMP, SESSION_TOKEN, EPHEMERAL_NONCE, USER_INPUT.
    """
    res = await _differential_uc.execute(task_id=task_id)
    data = {
        "task_id": res.task_id,
        "session_ids": res.session_ids,
        "classified_variables": res.classified_variables,
        "classified_tokens": res.classified_tokens,
        "classified_constants": res.classified_constants,
        "summary": res.summary,
        "variances": [
            {
                "path": v.path,
                "param_type": v.param_type.value if hasattr(v.param_type, "value") else str(v.param_type),
                "is_constant": v.is_constant,
                "inferred_purpose": v.inferred_purpose,
                "values_per_session": v.values_per_session,
            }
            for v in res.variances
        ],
    }
    return create_mcp_response(
        status="COMPLETED",
        data=data,
        result_count=len(res.variances),
        source="differential_analysis",
    )
