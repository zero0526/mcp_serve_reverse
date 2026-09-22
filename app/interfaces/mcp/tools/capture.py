import uuid
from typing import Any

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.capture.capture_status import CaptureStatusUseCase
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.interfaces.mcp.schemas.responses import create_mcp_response


def _get_capture_services():
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    ingest_uc = IngestEventUseCase(event_store=event_repo)
    start_uc = StartSessionUseCase(session_repository=session_repo, ingest_use_case=ingest_uc)
    stop_uc = StopSessionUseCase(session_repository=session_repo, active_browsers=start_uc.active_browsers)
    status_uc = CaptureStatusUseCase(session_repository=session_repo)
    return start_uc, stop_uc, status_uc


_start_uc, _stop_uc, _status_uc = _get_capture_services()


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
