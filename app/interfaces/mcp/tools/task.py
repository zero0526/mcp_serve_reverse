from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.session_log_repository import SQLiteSessionLogRepository
from app.adapters.persistence.sqlite.task_repository import SQLiteTaskRepository
from app.application.task.get_evolution_report import GetToolEvolutionReportUseCase
from app.application.task.get_task import GetTaskUseCase
from app.application.task.list_tasks import ListTasksUseCase
from app.application.task.record_retrospective import RecordTaskRetrospectiveUseCase
from app.application.task.update_task import UpdateTaskUseCase
from app.domain.task.entities import TaskStatus
from app.interfaces.mcp.schemas.responses import create_mcp_response

_task_repo = SQLiteTaskRepository(session_factory=AsyncSessionLocal)
_log_repo = SQLiteSessionLogRepository(session_factory=AsyncSessionLocal)

_get_task_uc = GetTaskUseCase(task_repository=_task_repo)
_list_tasks_uc = ListTasksUseCase(task_repository=_task_repo)
_update_task_uc = UpdateTaskUseCase(task_repository=_task_repo)
_record_retro_uc = RecordTaskRetrospectiveUseCase(session_log_repository=_log_repo)
_get_evolution_uc = GetToolEvolutionReportUseCase(session_log_repository=_log_repo)


async def get_task_tool(task_id: str) -> dict[str, Any]:
    """MCP Tool: Lấy thông tin chi tiết nhiệm vụ (Task) kèm mục tiêu, chỉ dẫn, env vars và các session IDs."""
    task = await _get_task_uc.execute(task_id=task_id)
    if not task:
        return create_mcp_response(
            status="NOT_FOUND",
            data={},
            session_id=task_id,
            warnings=[f"Không tìm thấy task '{task_id}'."],
            source="task_management",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=task.model_dump(),
        session_id=task_id,
        source="task_management",
    )


async def list_tasks_tool(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """MCP Tool: Liệt kê danh sách các Task có bộ lọc theo status."""
    safe_limit = max(1, min(limit, 100))
    tasks = await _list_tasks_uc.execute(status=status, limit=safe_limit, offset=offset)
    data = [t.model_dump() for t in tasks]
    return create_mcp_response(
        status="COMPLETED",
        data={"tasks": data, "count": len(data)},
        result_count=len(data),
        source="task_management",
    )


async def update_task_status_tool(
    task_id: str,
    status: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """MCP Tool: Cập nhật trạng thái nhiệm vụ (CREATED, IN_PROGRESS, COMPLETED, FAILED)."""
    normalized_status = status.upper()
    meta_update = {"notes": notes} if notes else None
    success = await _update_task_uc.execute(
        task_id=task_id, status=normalized_status, metadata_update=meta_update
    )
    if not success:
        return create_mcp_response(
            status="NOT_FOUND",
            data={"success": False},
            session_id=task_id,
            warnings=[f"Không tìm thấy task '{task_id}' để cập nhật."],
            source="task_management",
        )

    return create_mcp_response(
        status="COMPLETED",
        data={"success": True, "task_id": task_id, "status": normalized_status},
        session_id=task_id,
        source="task_management",
    )


async def record_task_retrospective_tool(
    task_id: str,
    agent_evaluation: str,
    missing_tools: list[str] | None = None,
    suggested_tools: list[dict[str, Any]] | None = None,
    bottlenecks: list[str] | None = None,
    efficiency_rating: int = 5,
    session_id: str | None = None,
) -> dict[str, Any]:
    """MCP Tool: Ghi nhận nhận xét hồi cứu của Agent về hiệu quả MCP Tools và đề xuất công cụ mới để tiến hóa."""
    log = await _record_retro_uc.execute(
        task_id=task_id,
        agent_evaluation=agent_evaluation,
        missing_tools=missing_tools,
        suggested_tools=suggested_tools,
        bottlenecks=bottlenecks,
        efficiency_rating=efficiency_rating,
        session_id=session_id,
    )
    return create_mcp_response(
        status="COMPLETED",
        data={
            "log_id": log.id,
            "task_id": task_id,
            "message": "Đã lưu nhận xét hồi cứu và đề xuất tiến hóa công cụ MCP.",
            "efficiency_rating": log.efficiency_rating,
        },
        session_id=task_id,
        source="mcp_evolution",
    )


async def get_tool_evolution_report_tool(task_id: str | None = None) -> dict[str, Any]:
    """MCP Tool: Tổng hợp báo cáo các công cụ MCP còn thiếu và đề xuất cải tiến từ nhật ký hồi cứu."""
    report = await _get_evolution_uc.execute(task_id=task_id)
    return create_mcp_response(
        status="COMPLETED",
        data=report,
        session_id=task_id,
        source="mcp_evolution",
    )
