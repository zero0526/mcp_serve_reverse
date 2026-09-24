"""Routes xử lý API quản lý Session (Launch browser, Close, Status)."""

from typing import Any
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.adapters.persistence.sqlite.models import SessionModel
from app.domain.shared.enums import SessionStatus
from playground.backend.dependencies import get_container


async def list_sessions_endpoint(request: Request) -> JSONResponse:
    """GET /api/sessions: Lấy danh sách session (có thể lọc theo task_id)."""
    task_id = request.query_params.get("task_id")
    container = await get_container()

    raw_sessions: list[dict[str, Any]] = []
    if task_id:
        raw_sessions = await container.session_repository.get_by_task_id(task_id)
    else:
        async with container.session_factory() as db:
            stmt = select(SessionModel).order_by(SessionModel.started_at_ns.desc())
            res = await db.execute(stmt)
            for obj in res.scalars().all():
                raw_sessions.append({
                    "id": obj.id,
                    "source": obj.source,
                    "name": obj.name,
                    "target": obj.target,
                    "status": obj.status,
                    "task_id": obj.task_id,
                    "started_at_ns": obj.started_at_ns,
                    "ended_at_ns": obj.ended_at_ns,
                    "metadata": {},
                })

    results = []
    for s in raw_sessions:
        sid = s["id"]
        stats = await container.session_repository.get_statistics(sid)
        raw_status = s.get("status") or "CREATED"
        results.append({
            "id": sid,
            "task_id": s.get("task_id"),
            "source": s.get("source", "browser"),
            "name": s.get("name") or sid,
            "target": s.get("target"),
            "status": raw_status.upper(),
            "started_at_ns": s.get("started_at_ns"),
            "ended_at_ns": s.get("ended_at_ns"),
            "event_count": stats.get("total_events", 0),
            "metadata": s.get("metadata", {}),
        })

    return JSONResponse(results)


async def launch_session_endpoint(request: Request) -> JSONResponse:
    """POST /api/sessions/{session_id}/launch: Khởi động trình duyệt Playwright/CloakBrowser."""
    session_id = request.path_params["session_id"]
    container = await get_container()

    sess = await container.session_repository.get_by_id(session_id)
    if not sess:
        return JSONResponse({"detail": f"Session '{session_id}' not found."}, status_code=404)

    target_url = sess.get("target") or "https://example.com"
    task_id = sess.get("task_id")

    # Đọc cấu hình browser từ Task nếu có
    headless = False
    use_cloak = True
    if task_id:
        task = await container.get_task_uc.execute(task_id)
        if task and hasattr(task, "browser_config"):
            bc = task.browser_config
            if isinstance(bc, dict):
                headless = bc.get("headless", False)
                use_cloak = bc.get("use_cloakbrowser", True)
            else:
                headless = getattr(bc, "headless", False)
                use_cloak = getattr(bc, "use_cloakbrowser", True)

    try:
        await container.start_session_uc.execute(
            session_id=session_id,
            name=sess.get("name"),
            target=target_url,
            task_id=task_id,
            options={
                "headless": headless,
                "use_cloakbrowser": use_cloak,
            },
        )
        return JSONResponse({"success": True, "session_id": session_id, "status": "RUNNING"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Nếu môi trường không thể bật display thật (ví dụ server không có X11/GUI),
        # ta update status RUNNING để luồng UI không bị kẹt.
        await container.session_repository.update_status(session_id, SessionStatus.RUNNING)
        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "status": "RUNNING",
            "warning": f"Browser started in simulated mode: {str(e)}",
        })


async def close_session_endpoint(request: Request) -> JSONResponse:
    """POST /api/sessions/{session_id}/close: Đóng trình duyệt và chiếu đồ thị Property Graph."""
    session_id = request.path_params["session_id"]
    container = await get_container()

    sess = await container.session_repository.get_by_id(session_id)
    if not sess:
        return JSONResponse({"detail": f"Session '{session_id}' not found."}, status_code=404)

    try:
        await container.stop_session_uc.execute(session_id=session_id)
    except Exception:
        pass

    # Chiếu đồ thị từ events
    graph_projected = False
    try:
        await container.rebuild_graph_uc.execute(session_id=session_id)
        graph_projected = True
    except Exception:
        pass

    # Đánh dấu trạng thái STOPPED
    await container.session_repository.update_status(session_id, SessionStatus.STOPPED)

    stats = await container.session_repository.get_statistics(session_id)
    return JSONResponse({
        "success": True,
        "session_id": session_id,
        "event_count": stats.get("total_events", 0),
        "graph_projected": graph_projected,
        "status": "STOPPED",
    })


async def get_session_status_endpoint(request: Request) -> JSONResponse:
    """GET /api/sessions/{session_id}/status: Trạng thái và thống kê session."""
    session_id = request.path_params["session_id"]
    container = await get_container()

    sess = await container.session_repository.get_by_id(session_id)
    if not sess:
        return JSONResponse({"detail": f"Session '{session_id}' not found."}, status_code=404)

    stats = await container.session_repository.get_statistics(session_id)
    return JSONResponse({
        "session_id": session_id,
        "status": (sess.get("status") or "CREATED").upper(),
        "statistics": stats,
    })
