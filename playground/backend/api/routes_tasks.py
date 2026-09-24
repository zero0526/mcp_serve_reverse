"""Routes xử lý API quản lý Task."""

from typing import Any
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.domain.task.entities import Task
from playground.backend.dependencies import get_container


def task_to_dict(task: Task) -> dict[str, Any]:
    """Chuyển đổi entity Task sang dictionary JSON-serializable."""
    b_conf = task.browser_config
    if hasattr(b_conf, "__dict__"):
        b_conf_dict = b_conf.__dict__
    elif isinstance(b_conf, dict):
        b_conf_dict = b_conf
    else:
        b_conf_dict = {}

    status_str = task.status.value if hasattr(task.status, "value") else str(task.status)

    return {
        "id": task.id,
        "name": task.name,
        "goal_description": task.goal_description,
        "instructions": task.instructions,
        "env_vars": task.env_vars or {},
        "initial_urls": task.initial_urls or [],
        "browser_config": b_conf_dict,
        "status": status_str,
        "session_ids": task.session_ids or [],
        "created_at_ns": task.created_at_ns,
        "updated_at_ns": task.updated_at_ns,
        "metadata": task.metadata or {},
    }


async def create_task_endpoint(request: Request) -> JSONResponse:
    """POST /api/tasks: Tạo mới Task kèm khởi tạo các session con."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    name = body.get("name")
    if not name:
        return JSONResponse({"detail": "Field 'name' is required."}, status_code=400)

    container = await get_container()
    task = await container.create_task_uc.execute(
        name=name,
        goal_description=body.get("goal_description", ""),
        instructions=body.get("instructions", ""),
        env_vars=body.get("env_vars"),
        initial_urls=body.get("initial_urls"),
        browser_config=body.get("browser_config"),
        task_id=body.get("task_id"),
        metadata=body.get("metadata"),
    )

    return JSONResponse(task_to_dict(task), status_code=201)


async def list_tasks_endpoint(request: Request) -> JSONResponse:
    """GET /api/tasks: Danh sách các task (có thể lọc theo status)."""
    status_filter = request.query_params.get("status")
    limit = int(request.query_params.get("limit", 100))
    offset = int(request.query_params.get("offset", 0))

    container = await get_container()
    tasks = await container.list_tasks_uc.execute(
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    return JSONResponse({
        "tasks": [task_to_dict(t) for t in tasks],
        "count": len(tasks),
    })


async def get_task_endpoint(request: Request) -> JSONResponse:
    """GET /api/tasks/{task_id}: Chi tiết một task."""
    task_id = request.path_params["task_id"]
    container = await get_container()
    task = await container.get_task_uc.execute(task_id)

    if not task:
        return JSONResponse({"detail": f"Task '{task_id}' not found."}, status_code=404)

    return JSONResponse(task_to_dict(task))


async def update_task_status_endpoint(request: Request) -> JSONResponse:
    """PATCH /api/tasks/{task_id}/status: Cập nhật trạng thái task."""
    task_id = request.path_params["task_id"]
    try:
        body = await request.json()
    except Exception:
        body = {}

    status = body.get("status")
    if not status:
        return JSONResponse({"detail": "Field 'status' is required."}, status_code=400)

    container = await get_container()
    meta_up = {"notes": body["notes"]} if body.get("notes") else None
    success = await container.update_task_uc.execute(
        task_id=task_id,
        status=status,
        metadata_update=meta_up,
    )

    if not success:
        return JSONResponse({"detail": f"Task '{task_id}' not found or update failed."}, status_code=404)

    return JSONResponse({"success": True, "task_id": task_id, "status": status})
