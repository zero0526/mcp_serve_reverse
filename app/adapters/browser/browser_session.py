import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from playwright.async_api import (
    Browser,
    BrowserContext,
    Frame,
    Page,
    Playwright,
    async_playwright,
)

from app.adapters.browser.js_bridge import JSBridge
from app.adapters.browser.network_mapper import NetworkMapper
from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope, PreSeedState
from app.infrastructure.config.settings import settings

INSTRUMENTATION_DIR = Path(__file__).parent / "instrumentation"


class BrowserSession:
    """Quản lý phiên Playwright Browser, cấy instrumentation linh hoạt và hỗ trợ multi-page/pre-seed."""

    def __init__(
        self,
        event_consumer: Callable[[EventEnvelope], Any],
        executable_path: str | None = None,
        headless: bool = True,
    ):
        self.event_consumer = event_consumer
        self.executable_path = executable_path
        self.headless = headless

        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._pages: list[Page] = []
        self._setup_page_ids: set[str] = set()
        self._bridge: JSBridge | None = None
        self._net_mapper: NetworkMapper | None = None
        self._drain_task: asyncio.Task | None = None
        self._is_running = False
        self._session_id: str | None = None
        self._options: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def page(self) -> Page | None:
        return self._page

    @property
    def pages(self) -> list[Page]:
        return [p for p in self._pages if not p.is_closed()]

    def _load_instrumentation_bundle(
        self,
        storage_seed_json: str | None = None,
        capture_options: dict[str, Any] | None = None,
    ) -> str:
        """Đọc và gộp các script instrumentation theo capture_options được chọn."""
        opts = capture_options or {}
        bundle_parts = []

        # 0. Thiết lập preamble: In-page event queue & emit function
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

        # 2. Cấu hình nạp script có chọn lọc dựa trên capture_options
        script_options = {
            "storage.js": opts.get("storage", True),
            "fetch.js": opts.get("network", True),
            "xhr.js": opts.get("network", True),
            "cookie.js": opts.get("cookies", True),
            "crypto.js": opts.get("crypto", True),
            "runtime.js": opts.get("runtime", True),
            "serializer.js": True,  # Luôn nạp serializer để hỗ trợ tuần tự hóa an toàn
        }

        for name, enabled in script_options.items():
            if not enabled:
                continue
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

    def _page_key(self, page: Page) -> str:
        impl = getattr(page, "_impl_obj", None)
        if impl and hasattr(impl, "_guid") and impl._guid:
            return str(impl._guid)
        return str(id(page))

    async def _setup_page(self, page: Page) -> None:
        """Cấy bridge, network mapper và listener cho từng page/tab."""
        pkey = self._page_key(page)
        if pkey in self._setup_page_ids:
            return
        self._setup_page_ids.add(pkey)

        if page not in self._pages:
            self._pages.append(page)
        page_id = getattr(page, "_guid", None) or pkey

        async def on_bridge_call(source, arg):
            if self._bridge:
                await self._bridge.handle_bridge_call(source, arg)

        try:
            await page.expose_binding("__api_lineage_bridge__", on_bridge_call)
        except Exception:
            pass

        if self._net_mapper:
            page.on("request", lambda req: asyncio.create_task(self._net_mapper.on_request(req, page_id=page_id)))
            page.on("response", lambda res: asyncio.create_task(self._net_mapper.on_response(res, page_id=page_id)))

        page.on("framenavigated", lambda frame: self._on_frame_navigated(frame, page_id=page_id))

        def on_page_close():
            self._setup_page_ids.discard(pkey)
            if page in self._pages:
                self._pages.remove(page)
            if self._page == page:
                active_pages = self.pages
                self._page = active_pages[0] if active_pages else None

        page.on("close", on_page_close)

    def _on_frame_navigated(self, frame: Frame, page_id: str) -> None:
        """Ghi nhận sự kiện điều hướng iframe / main frame nếu cần thiết."""
        pass

    async def _drain_queue(self) -> None:
        """Kéo toàn bộ sự kiện đang chờ trong hàng đợi in-page về backend trên tất cả các page mở."""
        for page in list(self._pages):
            if page.is_closed():
                continue
            try:
                events = await page.evaluate("""() => {
                    const q = window.__api_lineage_queue__ || [];
                    window.__api_lineage_queue__ = [];
                    return q;
                }""")
                if events and self._bridge:
                    page_id = getattr(page, "_guid", None) or str(id(page))
                    for item in events:
                        await self._bridge.handle_event_dict(item, page_id=page_id)
            except Exception:
                pass

    async def _drain_loop(self) -> None:
        """Vòng lặp drain định kỳ 50ms cho stealth browser."""
        while self._is_running:
            await self._drain_queue()
            await asyncio.sleep(0.05)

    async def sync_cookie_snapshot(self) -> list[dict[str, Any]]:
        """Đồng bộ toàn bộ cookie từ Playwright context (bao gồm HttpOnly) vào Event Store."""
        if not self._context:
            return []
        try:
            pw_cookies = await self._context.cookies()
            for c in pw_cookies:
                event_id = f"evt_ck_{uuid.uuid4().hex[:10]}"
                payload = {
                    "storage_type": "cookie",
                    "storage_key": c.get("name", ""),
                    "operation": "snapshot",
                    "value_preview": str(c.get("value", ""))[:512],
                    "domain": c.get("domain"),
                    "path": c.get("path"),
                    "http_only": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "same_site": c.get("sameSite"),
                    "expires": c.get("expires"),
                }
                envelope = EventEnvelope(
                    event_id=event_id,
                    schema_version=1,
                    session_id=self._session_id or "unknown_session",
                    source="browser",
                    event_type=EventType.STORAGE_WRITE,
                    timestamp_ns=time.time_ns(),
                    payload=payload,
                    metadata={"source": "playwright_context_cookies", "http_only": c.get("httpOnly", False)},
                )
                res = self.event_consumer(envelope)
                if hasattr(res, "__await__"):
                    await res
            return pw_cookies
        except Exception:
            return []

    async def capture_screenshot(self, target_path: Path | str | None = None) -> str | None:
        """Chụp ảnh màn hình trang hiện tại và lưu file artifact."""
        if not self._page or self._page.is_closed():
            return None
        try:
            if target_path:
                save_path = Path(target_path)
            else:
                session_folder = settings.sessions_dir / (self._session_id or "default")
                session_folder.mkdir(parents=True, exist_ok=True)
                save_path = session_folder / f"screenshot_{int(time.time())}.png"

            save_path.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(save_path), full_page=False)
            return str(save_path)
        except Exception:
            return None

    async def start(
        self,
        session_id: str,
        target: str | None = None,
        pre_seed_state: PreSeedState | None = None,
        options: dict[str, Any] | None = None,
    ) -> Page:
        """Khởi động Playwright, pre-seed state và điều hướng tới target nếu có."""
        self._session_id = session_id
        opts = options or {}
        self._options = opts
        headless = opts.get("headless", self.headless)
        use_cloak = opts.get("use_cloakbrowser", True)

        # Khởi động trình duyệt qua CloakBrowser (Stealth Chromium)
        if use_cloak:
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
                self._browser = None

        if not self._browser:
            # Fallback nếu CloakBrowser gặp lỗi môi trường hoặc bị tắt
            self._playwright = await async_playwright().start()
            if self.executable_path and Path(self.executable_path).exists():
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
            else:
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

        capture_opts = opts.get("capture_options") or opts
        bundle_code = self._load_instrumentation_bundle(storage_seed_json, capture_opts)
        await self._context.add_init_script(bundle_code)

        # 3. THIẾT LẬP JS BRIDGE & NETWORK MAPPER
        self._bridge = JSBridge(session_id=session_id, event_consumer=self.event_consumer)
        allowed_domains = opts.get("allowed_domains")
        filter_static = opts.get("filter_static", True)
        self._net_mapper = NetworkMapper(
            session_id=session_id,
            event_consumer=self.event_consumer,
            allowed_domains=allowed_domains,
            filter_static=filter_static,
        )

        # Lắng nghe mở tab/popup mới để tự động cấy bridge & listeners
        on_page_listener = self._context.on("page", lambda new_page: asyncio.create_task(self._setup_page(new_page)))
        if hasattr(on_page_listener, "__await__"):
            await on_page_listener

        # Tạo page đầu tiên
        self._page = await self._context.new_page()
        await self._setup_page(self._page)

        self._is_running = True
        self._drain_task = asyncio.create_task(self._drain_loop())

        # 4. ĐIỀU HƯỚNG NẾU CÓ TARGET
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

        for p in list(self._pages):
            try:
                if not p.is_closed():
                    await p.close()
            except Exception:
                pass
        self._pages.clear()

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
        self._net_mapper = None
