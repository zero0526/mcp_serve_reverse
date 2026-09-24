"""Routes xử lý API MCP Evolution & Retrospective."""

from starlette.requests import Request
from starlette.responses import JSONResponse

from playground.backend.dependencies import get_container


async def get_evolution_summary_endpoint(request: Request) -> JSONResponse:
    """GET /api/evolution/summary: Thống kê tổng hợp hồi cứu tiến hóa MCP tools."""
    task_id = request.query_params.get("task_id")
    container = await get_container()

    summary = await container.get_evolution_report_uc.execute(task_id=task_id)
    return JSONResponse(summary)


async def get_session_logs_endpoint(request: Request) -> JSONResponse:
    """GET /api/evolution/logs/{task_id}: Lấy danh sách hồi cứu của một Task."""
    task_id = request.path_params["task_id"]
    container = await get_container()

    logs = await container.session_log_repository.list_by_task_id(task_id)

    formatted_logs = []
    for log in logs:
        proposals_data = []
        for prop in log.suggested_tools:
            proposals_data.append({
                "name": prop.name,
                "purpose": prop.purpose,
                "parameters": prop.parameters or {},
                "expected_output": prop.expected_output,
                "task_id": getattr(prop, "task_id", log.task_id),
            })

        formatted_logs.append({
            "id": log.id,
            "task_id": log.task_id,
            "session_id": log.session_id,
            "log_type": log.log_type.value if hasattr(log.log_type, "value") else str(log.log_type),
            "agent_evaluation": log.agent_evaluation,
            "missing_tools": log.missing_tools or [],
            "suggested_tools": proposals_data,
            "bottlenecks": log.bottlenecks or [],
            "efficiency_rating": log.efficiency_rating,
            "created_at_ns": log.created_at_ns,
            "metadata": log.metadata or {},
        })

    return JSONResponse(formatted_logs)
