from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.application.network.analyze_request_lineage import AnalyzeRequestLineageUseCase
from app.application.network.compare_requests import CompareRequestsUseCase
from app.application.network.find_request_dependencies import FindRequestDependenciesUseCase
from app.application.network.summarize_request import SummarizeRequestUseCase
from app.interfaces.mcp.schemas.responses import create_mcp_response

_graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
_summarize_uc = SummarizeRequestUseCase(session_factory=AsyncSessionLocal)
_analyze_req_uc = AnalyzeRequestLineageUseCase(graph_repo=_graph_repo)
_find_dep_uc = FindRequestDependenciesUseCase(graph_repo=_graph_repo)
_compare_req_uc = CompareRequestsUseCase(session_factory=AsyncSessionLocal)


async def summarize_request_tool(
    session_id: str,
    request_id: str,
    include_headers: bool = True,
    include_response: bool = True,
    redaction_mode: str = "strict",
) -> dict[str, Any]:
    """MCP Tool: Tóm tắt HTTP Request, Response và tự động che giấu các thông tin bảo mật."""
    res = await _summarize_uc.execute(
        session_id=session_id,
        request_id=request_id,
        include_headers=include_headers,
        include_response=include_response,
        redaction_mode=redaction_mode,
    )
    if not res:
        return create_mcp_response(
            status="NOT_FOUND",
            data={},
            session_id=session_id,
            warnings=[f"Không tìm thấy request '{request_id}' trong session '{session_id}'."],
            source="network_analysis",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        redaction_mode=redaction_mode,
        source="network_analysis",
    )


async def analyze_request_lineage_tool(
    session_id: str,
    request_id: str,
    min_confidence: float = 0.8,
) -> dict[str, Any]:
    """MCP Tool: Phân tích toàn bộ nguồn gốc của các tham số cấu thành một request cụ thể."""
    res = await _analyze_req_uc.execute(
        session_id=session_id,
        request_id=request_id,
        min_confidence=min_confidence,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=len(res.get("parameters", [])),
        source="network_analysis",
    )


async def find_request_dependencies_tool(
    session_id: str,
    request_id: str,
    include_storage: bool = True,
    include_executions: bool = True,
    max_depth: int = 10,
) -> dict[str, Any]:
    """MCP Tool: Tìm các phụ thuộc (Dependencies) của request: storage, dispatcher, crypto, value."""
    res = await _find_dep_uc.execute(
        session_id=session_id,
        request_id=request_id,
        include_storage=include_storage,
        include_executions=include_executions,
        max_depth=max_depth,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res.get("total_dependencies", 0),
        source="network_analysis",
    )


async def compare_requests_tool(
    left_session_id: str,
    left_request_id: str,
    right_session_id: str,
    right_request_id: str,
    redaction_mode: str = "strict",
) -> dict[str, Any]:
    """MCP Tool: So sánh hai HTTP Request để tìm ra sự khác biệt về URL, method, headers, payload."""
    res = await _compare_req_uc.execute(
        left_session_id=left_session_id,
        left_request_id=left_request_id,
        right_session_id=right_session_id,
        right_request_id=right_request_id,
        redaction_mode=redaction_mode,
    )
    if res.get("status") == "NOT_FOUND":
        return create_mcp_response(
            status="NOT_FOUND",
            data=res,
            session_id=left_session_id,
            warnings=["Một trong hai request không tồn tại."],
            source="network_analysis",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=left_session_id,
        redaction_mode=redaction_mode,
        source="network_analysis",
    )
