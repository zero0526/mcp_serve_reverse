from cloakbrowser import ensure_binary
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import Browser as PWBrowser, Page as PWPage

from app.adapters.browser.browser_session import BrowserSession
from app.domain.trace.value_objects import EventEnvelope


@pytest.fixture
def dummy_event_consumer():
    events = []

    def consumer(envelope: EventEnvelope):
        events.append(envelope)

    consumer.events = events
    return consumer


class TestCloakBrowserInitialization:
    """Bộ test kiểm tra cấu hình, trạng thái binary và quá trình khởi tạo CloakBrowser."""

    def test_cloakbrowser_module_and_stealth_configuration(self):
        """Kiểm tra package cloakbrowser được cài đặt và nạp đúng các tham số stealth."""
        import cloakbrowser
        from cloakbrowser.config import (
            CHROMIUM_VERSION,
            IGNORE_DEFAULT_ARGS,
            get_default_stealth_args,
            get_download_url,
            get_platform_tag,
        )

        assert cloakbrowser.__version__ is not None
        platform_tag = get_platform_tag()
        assert platform_tag in ("windows-x64", "linux-x64", "darwin-arm64", "darwin-x64")

        download_url = get_download_url()
        assert "cloakbrowser" in download_url.lower()

        # Kiểm tra danh sách cờ stealth mặc định đã được vá
        stealth_args = get_default_stealth_args()
        assert any("--fingerprint=" in arg for arg in stealth_args)
        assert any("--fingerprint-platform=" in arg for arg in stealth_args)

        # Kiểm tra cờ --enable-automation bị loại trừ khỏi Chromium
        assert "--enable-automation" in IGNORE_DEFAULT_ARGS

    def test_cloakbrowser_humanize_behavior_configuration(self):
        """Kiểm tra cấu hình mô phỏng hành vi người dùng (mouse curve, typing delay, scroll)."""
        from cloakbrowser import HumanConfig

        config = HumanConfig()
        assert config.typing_delay > 0
        assert config.mouse_min_steps > 0
        assert config.mouse_overshoot_chance > 0
        assert config.idle_drift_px > 0

    def test_cloakbrowser_binary_cache_status(self):
        """Kiểm tra đường dẫn lưu trữ và trạng thái cache binary CloakBrowser trên hệ máy."""
        from cloakbrowser.config import get_binary_path, get_cache_dir

        cache_dir = get_cache_dir()
        binary_path = get_binary_path()

        assert cache_dir is not None
        assert binary_path is not None
        assert isinstance(binary_path, Path)

        # Kiểm tra xem binary đã tải về máy hay chưa
        is_downloaded = binary_path.exists()
        print(f"\n[CloakBrowser Binary Status] Path: {binary_path} | Cached: {is_downloaded}")

    @pytest.mark.asyncio
    async def test_browser_session_launches_cloakbrowser_when_available(
        self, dummy_event_consumer
    ):
        """Kiểm tra BrowserSession khởi tạo CloakBrowser thành công khi launch_async trả về browser."""
        mock_browser = MagicMock(spec=PWBrowser)
        mock_context = AsyncMock()
        mock_page = AsyncMock(spec=PWPage)

        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_context.add_init_script = AsyncMock()
        mock_context.add_cookies = AsyncMock()
        mock_page.expose_binding = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.is_closed.return_value = False
        mock_page.evaluate = AsyncMock(return_value=[])

        with patch("cloakbrowser.launch_async", new_callable=AsyncMock) as mock_launch:
            mock_launch.return_value = mock_browser

            session = BrowserSession(
                event_consumer=dummy_event_consumer,
                headless=True,
            )

            session_id = "test_cloak_sess_01"
            page = await session.start(
                session_id=session_id,
                options={"headless": True, "humanize": True},
            )

            assert page is not None
            assert session._browser is mock_browser
            assert session.is_running is True

            # Xác thực cloakbrowser.launch_async được gọi đúng tham số
            mock_launch.assert_awaited_once()
            call_kwargs = mock_launch.await_args.kwargs
            assert call_kwargs.get("headless") is True
            assert call_kwargs.get("humanize") is True
            assert "--disable-web-security" in call_kwargs.get("args", [])

            await session.stop()
            assert session.is_running is False

    @pytest.mark.asyncio
    async def test_browser_session_falls_back_to_playwright_on_cloak_failure(
        self, dummy_event_consumer
    ):
        """Kiểm tra BrowserSession bắt lỗi khi CloakBrowser thất bại và fallback an toàn sang standard Playwright."""
        with patch(
            "cloakbrowser.launch_async",
            side_effect=RuntimeError("CloakBrowser binary not cached or download timeout"),
        ) as mock_launch:
            session = BrowserSession(
                event_consumer=dummy_event_consumer,
                headless=True,
            )

            session_id = "test_fallback_sess_02"
            page = await session.start(
                session_id=session_id,
                options={"headless": True},
            )

            assert page is not None
            # Xác nhận session vẫn chạy ổn định nhờ fallback Playwright
            assert session.is_running is True
            assert session._playwright is not None
            assert session._browser is not None

            # Kiểm tra page hoạt động tốt với evaluate JavaScript
            val = await page.evaluate("() => 10 + 20")
            assert val == 30

            await session.stop()
            assert session.is_running is False

    @pytest.mark.asyncio
    async def test_cloakbrowser_direct_launch_or_skip(self):
        """Thử nghiệm khởi chạy trực tiếp CloakBrowser nếu binary đã tồn tại, hoặc kiểm tra phát hiện thiếu binary."""
   
        from cloakbrowser import launch_async
        from cloakbrowser.config import get_binary_path

        binary_path = get_binary_path()

        if binary_path.exists():
            # Nếu binary đã có sẵn trong máy -> Test khởi chạy thật
            browser = await launch_async(headless=True)
            try:
                page = await browser.new_page()
                # Kiểm tra tính năng stealth: navigator.webdriver phải là False
                webdriver_flag = await page.evaluate("() => navigator.webdriver")
                assert webdriver_flag is False, "CloakBrowser stealth patch must hide navigator.webdriver"
                await page.close()
            finally:
                await browser.close()
        else:
            # Nếu binary chưa tải về (~562MB) -> Xác nhận binary_path không tồn tại
            pytest.skip(
                f"CloakBrowser custom binary (~562MB) is not yet cached at {binary_path}. "
                "Download is required before running native binary execution test."
            )
