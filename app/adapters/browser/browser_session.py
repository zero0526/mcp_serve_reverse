import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.adapters.browser.js_bridge import JSBridge
from app.adapters.browser.network_mapper import NetworkMapper
from app.domain.trace.value_objects import EventEnvelope, PreSeedState

INSTRUMENTATION_DIR = Path(__file__).parent / "instrumentation"


class BrowserSession:
    """Quản lý phiên Playwright Browser, cấy instrumentation và hỗ trợ pre-seed state."""

    def __init__(
        self,
        event_consumer: Callable[[EventEnvelope], Any],
        executable_path: str = "/usr/bin/google-chrome",
        headless: bool = True,
    ):
        self.event_consumer = event_consumer
        self.executable_path = executable_path
        self.headless = headless

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._bridge: JSBridge | None = None
        self._drain_task: asyncio.Task | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def page(self) -> Page | None:
        return self._page

    def _load_instrumentation_bundle(self, storage_seed_json: str | None = None) -> str:
        """Đọc và gộp toàn bộ các script instrumentation thành một bundle."""
        bundle_parts = []

        # 0. Thiết lập preamble: In-page event queue & emit function
        # Hoạt động mượt mà cả trên Stealth Chromium (CloakBrowser) và Standard Playwright
        bundle_parts.append(
            "(() => {\n"
            "  window.__api_lineage_queue__ = window.__api_lineage_queue__ || [];\n"
            "  window.__api_lineage_emit__ = function(eventType, payload, stack) {\n"
            "    try {\n"
            "      const evt = {\n"
            "        event_type: eventType,\n"
            "        timestamp_ms: Date.now(),\n"
            "        stack: stack || null,\n"
            "        payload: payload,\n"
            "      };\n"
            "      window.__api_lineage_queue__.push(evt);\n"
            "      if (typeof window.__api_lineage_bridge__ === 'function') {\n"
            "        try { window.__api_lineage_bridge__(JSON.stringify(evt)); } catch(e) {}\n"
            "      }\n"
            "    } catch(e) {}\n"
            "  };\n"
            "})();\n"
        )

        # 1. Thêm hàm tự động apply pre-seed nếu có
        if storage_seed_json:
            bundle_parts.append(
                f"window.__api_lineage_seed_data__ = {storage_seed_json};\n"
            )

        # 2. Đọc từng file instrumentation theo thứ tự ưu tiên
        script_names = ["storage.js", "fetch.js", "xhr.js", "cookie.js", "crypto.js", "runtime.js", "serializer.js"]
        for name in script_names:
            script_path = INSTRUMENTATION_DIR / name
            if script_path.exists():
                bundle_parts.append(script_path.read_text(encoding="utf-8"))

        # 3. Kích hoạt apply pre-seed ngay sau khi hook storage đã sẵn sàng
        if storage_seed_json:
            bundle_parts.append(
                "if (typeof window.__api_lineage_apply_preseed__ === 'function') { "
                "window.__api_lineage_apply_preseed__(window.__api_lineage_seed_data__); }\n"
            )

        return "\n\n".join(bundle_parts)

    async def _drain_queue(self) -> None:
        """Kéo toàn bộ sự kiện đang chờ trong hàng đợi in-page về Python backend."""
        if not self._page or self._page.is_closed():
            return
        try:
            events = await self._page.evaluate("""() => {
                const q = window.__api_lineage_queue__ || [];
                window.__api_lineage_queue__ = [];
                return q;
            }""")
            if events and self._bridge:
                page_id = getattr(self._page, "_guid", None) or str(id(self._page))
                for item in events:
                    await self._bridge.handle_event_dict(item, page_id=page_id)
        except Exception:
            pass

    async def _drain_loop(self) -> None:
        """Vòng lặp drain định kỳ 50ms cho stealth browser."""
        while self._is_running:
            await self._drain_queue()
            await asyncio.sleep(0.05)

    async def start(
        self,
        session_id: str,
        target: str | None = None,
        pre_seed_state: PreSeedState | None = None,
        options: dict[str, Any] | None = None,
    ) -> Page:
        """Khởi động Playwright, pre-seed state và điều hướng tới target nếu có."""
        opts = options or {}
        headless = opts.get("headless", self.headless)

        # Khởi động trình duyệt qua CloakBrowser (Stealth Chromium)
        try:
            from cloakbrowser import launch_async

            humanize = opts.get("humanize", True)
            proxy = opts.get("proxy")
            extra_args = ["--disable-web-security", "--no-sandbox"]

            self._browser = await launch_async(
                headless=headless,
                proxy=proxy,
                humanize=humanize,
                args=extra_args,
            )
        except Exception:
            # Fallback nếu CloakBrowser gặp lỗi môi trường
            self._playwright = await async_playwright().start()
            try:
                self._browser = await self._playwright.chromium.launch(
                    executable_path=self.executable_path,
                    headless=headless,
                    args=["--disable-web-security", "--no-sandbox"],
                )
            except Exception:
                self._browser = await self._playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-web-security", "--no-sandbox"],
                )

        # Tạo context (hỗ trợ storage_state_path nếu người dùng cung cấp file sẵn)
        context_kwargs: dict[str, Any] = {
            "ignore_https_errors": True,
            "viewport": {"width": 1280, "height": 800},
        }
        if pre_seed_state and pre_seed_state.storage_state_path:
            context_kwargs["storage_state"] = pre_seed_state.storage_state_path

        self._context = await self._browser.new_context(**context_kwargs)

        # 1. PRE-SEED COOKIES nếu có
        if pre_seed_state and pre_seed_state.cookies:
            pw_cookies = []
            for c in pre_seed_state.cookies:
                cookie_dict = {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "httpOnly": c.http_only,
                    "secure": c.secure,
                    "sameSite": c.same_site,
                }
                pw_cookies.append(cookie_dict)
            await self._context.add_cookies(pw_cookies)

        # 2. PREPARE INSTRUMENTATION & STORAGE SEED
        storage_seed_json = None
        if pre_seed_state and (
            pre_seed_state.storage.local_storage or pre_seed_state.storage.session_storage
        ):
            storage_seed_json = json.dumps(pre_seed_state.storage.model_dump())

        bundle_code = self._load_instrumentation_bundle(storage_seed_json)
        await self._context.add_init_script(bundle_code)

        # Tạo page
        self._page = await self._context.new_page()

        # 3. THIẾT LẬP JS BRIDGE & EVENT DRAIN
        self._bridge = JSBridge(session_id=session_id, event_consumer=self.event_consumer)

        async def on_bridge_call(source, arg):
            if self._bridge:
                await self._bridge.handle_bridge_call(source, arg)

        try:
            await self._page.expose_binding(
                "__api_lineage_bridge__",
                on_bridge_call,
            )
        except Exception:
            pass

        # 4. THIẾT LẬP NETWORK MAPPER
        net_mapper = NetworkMapper(session_id=session_id, event_consumer=self.event_consumer)
        self._page.on("request", lambda req: net_mapper.on_request(req))
        self._page.on("response", lambda res: net_mapper.on_response(res))

        self._is_running = True
        self._drain_task = asyncio.create_task(self._drain_loop())

        # 5. ĐIỀU HƯỚNG NẾU CÓ TARGET
        if target:
            try:
                await self._page.goto(target, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

        return self._page

    async def navigate(self, url: str) -> None:
        if self._page:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def stop(self) -> None:
        """Đóng session và dọn dẹp tiến trình browser."""
        self._is_running = False
        if self._drain_task:
            try:
                await asyncio.wait_for(self._drain_task, timeout=2.0)
            except Exception:
                pass
            self._drain_task = None

        # Drain bất kỳ sự kiện nào còn lại trong in-page queue trước khi đóng page
        await self._drain_queue()

        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._bridge = None
