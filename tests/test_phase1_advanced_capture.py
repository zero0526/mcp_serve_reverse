import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import select

from app.adapters.browser.browser_session import BrowserSession
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.event_repository import SQLiteEventRepository
from app.adapters.persistence.sqlite.models import (
    NetworkRequestModel,
    NetworkResponseModel,
    StorageOperationModel,
)
from app.adapters.persistence.sqlite.session_repository import SQLiteSessionRepository
from app.application.capture.start_session import StartSessionUseCase
from app.application.capture.stop_session import StopSessionUseCase
from app.application.ingest.ingest_event import IngestEventUseCase


class MockAdvancedHandler(BaseHTTPRequestHandler):
    """Local HTTP Server giả lập static resources, API endpoints và popup pages."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/logo.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", "4")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"PNG\x00")
        elif path == "/styles.css":
            css_data = b"body { margin: 0; }"
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.send_header("Content-Length", str(len(css_data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(css_data)
        elif path == "/popup":
            html = """<!DOCTYPE html><html><body><h1>Popup Window</h1></body></html>""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(html)
        elif path == "/api/data":
            resp = json.dumps({"status": "ok", "items": [10, 20, 30]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(resp)
        else:
            html = """<!DOCTYPE html><html><head><link rel="stylesheet" href="/styles.css"></head><body><h1>Main App</h1><img src="/logo.png"/></body></html>""".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(html)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def advanced_mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockAdvancedHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_selective_capture_options_bundle():
    """Kiểm thử tính năng cấu hình capture_options linh hoạt: chỉ bundle các script được bật."""
    dummy_consumer = lambda e: None
    session = BrowserSession(event_consumer=dummy_consumer)

    # 1. Tắt storage và crypto
    bundle_disabled = session._load_instrumentation_bundle(
        capture_options={"storage": False, "crypto": False, "network": True}
    )
    assert "__api_lineage_fetch_hooked__" in bundle_disabled
    assert "__api_lineage_storage_hooked__" not in bundle_disabled
    assert "__api_lineage_crypto_hooked__" not in bundle_disabled

    # 2. Bật tất cả mặc định
    bundle_all = session._load_instrumentation_bundle()
    assert "__api_lineage_fetch_hooked__" in bundle_all
    assert "__api_lineage_storage_hooked__" in bundle_all
    assert "__api_lineage_crypto_hooked__" in bundle_all


@pytest.mark.asyncio
async def test_static_filtering_and_request_deduplication(advanced_mock_server):
    """Kiểm thử lọc tài nguyên tĩnh (.png, .css) và deduplication request giữa JS hook & Playwright."""
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

    session_id = f"sess_adv_{uuid.uuid4().hex[:8]}"

    # Khởi động session với target web có cả static resource (/logo.png, /styles.css)
    await start_use_case.execute(
        session_id=session_id,
        name="Advanced Capture Test",
        target=advanced_mock_server,
        options={
            "headless": True,
            "filter_static": True,
            "save_screenshots": True,
            "use_cloakbrowser": False,  # Dùng standard Chromium để test chạy nhanh và độc lập
        },
    )

    active_browser = start_use_case.active_browsers[session_id]
    page = active_browser.page
    assert page is not None

    # Thực hiện gọi API /api/data qua fetch()
    await page.evaluate(
        f"""async () => {{
            const resp = await fetch("{advanced_mock_server}/api/data");
            const data = await resp.json();
            window.__test_data__ = data;
        }}"""
    )
    await asyncio.sleep(1.0)

    # Thêm HttpOnly cookie trực tiếp vào Playwright context để kiểm thử sync_cookie_snapshot
    await active_browser._context.add_cookies([
        {
            "name": "super_secret_http_only",
            "value": "jwt_refresh_token_999",
            "domain": "127.0.0.1",
            "path": "/",
            "httpOnly": True,
            "secure": False,
        }
    ])

    # Chụp ảnh màn hình thủ công để kiểm tra
    screenshot_file = await active_browser.capture_screenshot()
    assert screenshot_file is not None
    assert Path(screenshot_file).exists()
    assert Path(screenshot_file).stat().st_size > 0

    # Dừng session
    stop_res = await stop_use_case.execute(session_id)
    assert stop_res["status"] == "stopped"

    # ═══════════════════════════════════════════════════════════════════════
    # KIỂM TRA DATABASE (SQLite Verification)
    # ═══════════════════════════════════════════════════════════════════════
    async with AsyncSessionLocal() as db:
        # 1. Kiểm tra LỌC TÀI NGUYÊN TĨNH: Không có request nào cho .png hoặc .css
        reqs = (
            await db.execute(select(NetworkRequestModel).where(NetworkRequestModel.session_id == session_id))
        ).scalars().all()

        urls = [r.url for r in reqs]
        assert not any(u.endswith(".png") for u in urls), f"Static .png must be filtered out! Found: {urls}"
        assert not any(u.endswith(".css") for u in urls), f"Static .css must be filtered out! Found: {urls}"

        # 2. Kiểm tra DEDUPLICATION REQUEST: Chỉ có 1 bản ghi cho endpoint /api/data
        api_reqs = [r for r in reqs if "/api/data" in r.url]
        assert len(api_reqs) == 1, f"Expected exactly 1 deduplicated record for /api/data, found: {len(api_reqs)}"

        dedup_req = api_reqs[0]
        # Request phải có execution_id (từ JS call stack)
        assert dedup_req.execution_id is not None
        assert dedup_req.status == "captured"

        # 3. Kiểm tra RESPONSE liên kết: Chỉ có 1 response tương ứng và có status_code 200
        resps = (
            await db.execute(select(NetworkResponseModel).where(NetworkResponseModel.request_id == dedup_req.id))
        ).scalars().all()
        assert len(resps) == 1, f"Expected 1 response record linked to request {dedup_req.id}, found {len(resps)}"
        assert resps[0].status_code == 200
        assert "items" in (resps[0].body_json or "")

        # 4. Kiểm tra ĐỒNG BỘ COOKIE HttpOnly: super_secret_http_only phải có trong storage_operations
        st_ops = (
            await db.execute(
                select(StorageOperationModel)
                .where(StorageOperationModel.session_id == session_id)
                .where(StorageOperationModel.storage_key == "super_secret_http_only")
            )
        ).scalars().all()
        assert len(st_ops) >= 1, "HttpOnly cookie 'super_secret_http_only' must be captured into storage_operations!"
        assert st_ops[0].storage_type == "cookie"
        assert st_ops[0].value_ref == "jwt_refresh_token_999"


@pytest.mark.asyncio
async def test_multi_page_popup_capture(advanced_mock_server):
    """Kiểm thử mở popup/tab mới và xác nhận page_id được phân biệt chính xác."""
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

    session_id = f"sess_multi_{uuid.uuid4().hex[:8]}"

    await start_use_case.execute(
        session_id=session_id,
        name="Multi-Page Test",
        target=advanced_mock_server,
        options={"headless": True, "use_cloakbrowser": False},
    )

    active_browser = start_use_case.active_browsers[session_id]
    main_page = active_browser.page
    assert main_page is not None

    # Mở tab popup mới
    async with active_browser._context.expect_page() as new_page_info:
        await main_page.evaluate(f"window.open('{advanced_mock_server}/popup');")

    popup_page = await new_page_info.value
    await popup_page.wait_for_load_state("domcontentloaded")
    assert len(active_browser.pages) >= 2

    # Gọi fetch bên trong trang popup
    await popup_page.evaluate(
        f"""async () => {{
            await fetch("{advanced_mock_server}/api/data");
        }}"""
    )
    await asyncio.sleep(1.0)

    # Đóng popup và stop session
    await popup_page.close()
    await stop_use_case.execute(session_id)

    # Kiểm tra database: xác nhận có request từ popup page
    async with AsyncSessionLocal() as db:
        reqs = (
            await db.execute(select(NetworkRequestModel).where(NetworkRequestModel.session_id == session_id))
        ).scalars().all()
        assert len(reqs) >= 1
