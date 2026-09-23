from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.application.trace.get_execution_context import GetExecutionContextUseCase
from app.application.trace.get_timeline import GetTraceTimelineUseCase
from app.application.trace.search_events import SearchTraceEventsUseCase
from app.interfaces.mcp.schemas.responses import create_mcp_response

_search_uc = SearchTraceEventsUseCase(session_factory=AsyncSessionLocal)
_timeline_uc = GetTraceTimelineUseCase(session_factory=AsyncSessionLocal)
_context_uc = GetExecutionContextUseCase(session_factory=AsyncSessionLocal)


async def search_trace_events_tool(
    session_id: str,
    event_types: list[str] | None = None,
    page_id: str | None = None,
    start_ns: int | None = None,
    end_ns: int | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """MCP Tool: Tìm kiếm các sự kiện vết (Trace Events) gốc theo loại, thời gian, từ khóa."""
    safe_limit = max(1, min(limit, 500))
    res = await _search_uc.execute(
        session_id=session_id,
        event_types=event_types,
        page_id=page_id,
        start_ns=start_ns,
        end_ns=end_ns,
        keyword=keyword,
        limit=safe_limit,
        offset=offset,
    )
    is_truncated = (offset + len(res["events"])) < res["total_count"]
    return create_mcp_response(
        status="COMPLETED" if not is_truncated else "PARTIAL",
        data=res,
        session_id=session_id,
        result_count=len(res["events"]),
        truncated=is_truncated,
        source="trace_event_store",
    )


async def get_trace_timeline_tool(
    session_id: str,
    event_types: list[str] | None = None,
    start_ns: int | None = None,
    end_ns: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """MCP Tool: Lấy dòng thời gian chuỗi sự kiện đã chuẩn hóa theo thứ tự thực thi."""
    safe_limit = max(1, min(limit, 500))
    res = await _timeline_uc.execute(
        session_id=session_id,
        event_types=event_types,
        start_ns=start_ns,
        end_ns=end_ns,
        limit=safe_limit,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res["count"],
        source="trace_event_store",
    )


async def get_execution_context_tool(
    session_id: str,
    execution_id: str,
    include_arguments: bool = True,
    include_return_value: bool = True,
    include_stack_trace: bool = True,
    include_related_network: bool = True,
    include_call_tree: bool = True,
    max_related_events: int = 30,
) -> dict[str, Any]:
    """MCP Tool: Lấy context chi tiết của một lần thực thi hàm (caller/callee tree, args, return value, stack, network)."""
    res = await _context_uc.execute(
        session_id=session_id,
        execution_id=execution_id,
        include_arguments=include_arguments,
        include_return_value=include_return_value,
        include_stack_trace=include_stack_trace,
        include_related_network=include_related_network,
        include_call_tree=include_call_tree,
        max_related_events=max_related_events,
    )
    return create_mcp_response(
        status="COMPLETED" if res.get("found", True) else "NOT_FOUND",
        data=res,
        session_id=session_id,
        result_count=1 if res.get("found", True) else 0,
        source="trace_execution_context",
    )
