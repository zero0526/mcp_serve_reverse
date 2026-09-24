import uuid
from typing import Any
from sqlalchemy import select

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.models import SessionModel
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.capture.capture_status import CaptureStatusUseCase
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.interfaces.mcp.schemas.responses import create_mcp_response

_session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
_event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
_ingest_uc = IngestEventUseCase(event_store=_event_repo)
_start_uc = StartSessionUseCase(session_repository=_session_repo, ingest_use_case=_ingest_uc)
_stop_uc = StopSessionUseCase(session_repository=_session_repo, active_browsers=_start_uc.active_browsers)
_status_uc = CaptureStatusUseCase(session_repository=_session_repo)


async def start_capture_session_tool(
    name: str,
    target: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MCP Tool: Bắt đầu một phiên thu thập dữ liệu (Browser Capture Session)."""
    sid = session_id or f"sess_{uuid.uuid4().hex[:8]}"
    tid = task_id or f"task_{uuid.uuid4().hex[:8]}"
    opts = options or {"headless": True}

    res = await _start_uc.execute(
        session_id=sid,
        name=name,
        target=target,
        task_id=tid,
        options=opts,
    )
    return create_mcp_response(
        status="COMPLETED",
        data={
            "session_id": sid,
            "task_id": tid,
            "name": name,
            "target": target,
            "status": "RUNNING",
            "browser_pid": res.get("browser_pid"),
        },
        session_id=sid,
        source="browser_capture",
    )


async def stop_capture_session_tool(session_id: str) -> dict[str, Any]:
    """MCP Tool: Dừng phiên thu thập dữ liệu và đóng trình duyệt."""
    res = await _stop_uc.execute(session_id)
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        source="browser_capture",
    )


async def get_capture_status_tool(session_id: str) -> dict[str, Any]:
    """MCP Tool: Xem trạng thái và các số liệu thống kê của phiên capture."""
    status = await _status_uc.get_session_status(session_id)
    if not status:
        return create_mcp_response(
            status="NOT_FOUND",
            data={},
            session_id=session_id,
            warnings=[f"Không tìm thấy phiên capture '{session_id}'."],
            source="browser_capture",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=status,
        session_id=session_id,
        source="browser_capture",
    )


async def list_sessions_tool(
    task_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """MCP Tool: Liệt kê danh sách các phiên capture (Sessions) có metadata và số lượng sự kiện."""
    raw_sessions = []
    if task_id:
        raw_sessions = await _session_repo.get_by_task_id(task_id)
    else:
        async with _session_repo.session_factory() as db:
            stmt = select(SessionModel).order_by(SessionModel.started_at_ns.desc()).limit(limit).offset(offset)
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
                })

    sessions_data = []
    for s in raw_sessions:
        stats = await _session_repo.get_statistics(s["id"])
        sessions_data.append({
            "id": s["id"],
            "session_id": s["id"],
            "task_id": s.get("task_id"),
            "name": s.get("name"),
            "target": s.get("target"),
            "status": (s.get("status") or "CREATED").upper(),
            "started_at_ns": s.get("started_at_ns"),
            "ended_at_ns": s.get("ended_at_ns"),
            "event_count": stats.get("total_events", 0),
            "requests_count": stats.get("network_requests", 0),
        })

    return create_mcp_response(
        status="COMPLETED",
        data={"sessions": sessions_data, "total_count": len(sessions_data)},
        result_count=len(sessions_data),
        source="session_discovery",
    )
