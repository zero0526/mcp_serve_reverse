import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.capture.capture_status import CaptureStatusUseCase
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.ingest.ingest_event import IngestEventUseCase
from app.domain.trace.value_objects import CookieSeed, PreSeedState, StorageSeed


class MockWebHandler(BaseHTTPRequestHandler):
    """Local HTTP Server giả lập trang web và API đổi tên."""

    last_post_body: ClassVar[bytes | None] = None

    def do_GET(self):
        html = """<!DOCTYPE html><html><head><title>Test App</title></head><body><h1>Account Settings</h1><div id="status">Ready</div></body></html>""".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        MockWebHandler.last_post_body = body

        resp_bytes = json.dumps({"status": "success", "updated": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(resp_bytes)

    def log_message(self, format, *args):
        pass  # Tắt log stdout khi test chạy


@pytest.fixture(scope="module")
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockWebHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_phase1_multi_session_capture(mock_server):
    # 1. Khởi tạo Repositories & Use Cases
    session_repo = SQLiteSessionRepository(session_factory=AsyncSessionLocal)
    event_repo = SQLiteEventRepository(session_factory=AsyncSessionLocal)
    ingest_use_case = IngestEventUseCase(event_store=event_repo)

    start_use_case = StartSessionUseCase(
        session_repository=session_repo,
        ingest_use_case=ingest_use_case,
    )
    stop_use_case = StopSessionUseCase(
        session_repository=session_repo,
        active_browsers=start_use_case.active_browsers,
    )
    status_use_case = CaptureStatusUseCase(session_repository=session_repo)

    task_id = f"task_test_rename_{uuid.uuid4().hex[:8]}"

    # ═══════════════════════════════════════════════════════════════════════
    # SESSION 1: Đổi tên thành "Nguyen An" với auth_token_AAA
    # ═══════════════════════════════════════════════════════════════════════
    session_1_id = f"sess_1_{uuid.uuid4().hex[:8]}"
    seed_1 = PreSeedState(
        cookies=[
            CookieSeed(name="c_user", value="10001", domain="127.0.0.1"),
            CookieSeed(name="xs", value="secret_xs_token", domain="127.0.0.1"),
        ],
        storage=StorageSeed(
            local_storage={"auth_token": "token_AAA", "device_id": "dev_001"},
            session_storage={"tab_id": "tab_1"},
        ),
    )

    await start_use_case.execute(
        session_id=session_1_id,
        name="Session 1 - Rename An",
        target=mock_server,
        task_id=task_id,
        pre_seed_state=seed_1,
        options={"headless": True},
    )

    page_1 = start_use_case.active_browsers[session_1_id].page
    assert page_1 is not None

    # Thực hiện thao tác trong browser:
    # Đọc token pre-seed -> gọi fetch POST -> ghi storage mới
    await page_1.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            const res = await fetch("{mock_server}/api/rename", {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + token
                }},
                body: JSON.stringify({{ name: "Nguyen An", timestamp: Date.now() }})
            }});
            localStorage.setItem("last_action", "renamed_to_an");
        }}"""
    )
    await asyncio.sleep(1.0)  # Đợi bridge và network handler xử lý

    res_stop_1 = await stop_use_case.execute(session_1_id)
    assert res_stop_1["status"] == "stopped"

    # ═══════════════════════════════════════════════════════════════════════
    # SESSION 2: Đổi tên thành "Tran Binh" với auth_token_BBB
    # ═══════════════════════════════════════════════════════════════════════
    session_2_id = f"sess_2_{uuid.uuid4().hex[:8]}"
    seed_2 = PreSeedState(
        cookies=[
            CookieSeed(name="c_user", value="10001", domain="127.0.0.1"),
        ],
        storage=StorageSeed(
            local_storage={"auth_token": "token_BBB", "device_id": "dev_001"},
        ),
    )

    await start_use_case.execute(
        session_id=session_2_id,
        name="Session 2 - Rename Binh",
        target=mock_server,
        task_id=task_id,
        pre_seed_state=seed_2,
        options={"headless": True},
    )

    page_2 = start_use_case.active_browsers[session_2_id].page
    assert page_2 is not None

    # Thực hiện thao tác với input khác
    await page_2.evaluate(
        f"""async () => {{
            const token = localStorage.getItem("auth_token");
            await fetch("{mock_server}/api/rename", {{
                method: "POST",
                headers: {{
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + token
                }},
                body: JSON.stringify({{ name: "Tran Binh", timestamp: Date.now() }})
            }});
            localStorage.setItem("last_action", "renamed_to_binh");
        }}"""
    )
    await asyncio.sleep(1.0)

    res_stop_2 = await stop_use_case.execute(session_2_id)
    assert res_stop_2["status"] == "stopped"

    # ═══════════════════════════════════════════════════════════════════════
    # VERIFICATION: Kiểm tra tính toàn vẹn và khả năng phân biệt dữ liệu
    # ═══════════════════════════════════════════════════════════════════════

    # 1. Kiểm tra gom nhóm theo Task: cả 2 session đều phải thuộc task_id
    task_sessions = await status_use_case.get_task_sessions(task_id)
    assert len(task_sessions) == 2
    session_ids = [s["id"] for s in task_sessions]
    assert session_1_id in session_ids
    assert session_2_id in session_ids

    for s in task_sessions:
        print(f"DEBUG SESSION {s['id']} STATS:", s["statistics"])
        assert s["status"] == "stopped"
        assert s["statistics"]["total_events"] > 0
        assert s["statistics"]["network_requests"] > 0
        assert s["statistics"]["storage_operations"] > 0

    # 2. Kiểm tra trace events của Session 1
    events_1 = await event_repo.search_events(session_1_id, limit=100)
    event_types_1 = [e["event_type"] for e in events_1]
    assert "storage_read" in event_types_1
    assert "storage_write" in event_types_1
    assert "network_request" in event_types_1

    # 3. Kiểm tra bảo mật Redaction: Header Authorization phải bị che giấu
    net_events_1 = [e for e in events_1 if e["event_type"] == "network_request"]
    auth_redacted = False
    for ne in net_events_1:
        headers = ne["payload"].get("headers", {})
        auth_val = headers.get("authorization") or headers.get("Authorization")
        if auth_val:
            assert "[REDACTED:sha256:" in auth_val
            auth_redacted = True
    assert auth_redacted, "Authorization header must be redacted!"

    # 4. Kiểm tra sự khác biệt giữa 2 session (chuẩn bị cho Phase 2 & 3 Differential Analysis)
    events_2 = await event_repo.search_events(session_2_id, limit=100)
    post_requests_1 = [
        e for e in events_1
        if e["event_type"] == "network_request" and e["payload"].get("method") == "POST"
    ]
    post_requests_2 = [
        e for e in events_2
        if e["event_type"] == "network_request" and e["payload"].get("method") == "POST"
    ]

    assert len(post_requests_1) >= 1
    assert len(post_requests_2) >= 1

    body_1 = str(post_requests_1[0]["payload"].get("body") or post_requests_1[0]["payload"].get("post_data"))
    body_2 = str(post_requests_2[0]["payload"].get("body") or post_requests_2[0]["payload"].get("post_data"))

    assert "Nguyen An" in body_1
    assert "Tran Binh" in body_2
    assert body_1 != body_2, "Two sessions must capture distinct input variations!"
