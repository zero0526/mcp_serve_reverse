import time
import uuid
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Request as PWRequest, Response as PWResponse

from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope

STATIC_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".css", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".webm", ".avi", ".mov", ".map"
)

STATIC_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

TRACKING_DOMAINS = (
    "google-analytics.com",
    "googletagmanager.com",
    "sentry.io",
    "doubleclick.net",
    "facebook.net",
    "clarity.ms",
    "hotjar.com",
    "segment.io",
    "mixpanel.com",
)


class NetworkMapper:
    """Mapper lắng nghe sự kiện mạng tầng Playwright, lọc rác và đóng gói thành EventEnvelope."""

    def __init__(
        self,
        session_id: str,
        event_consumer: Callable[[EventEnvelope], Any],
        allowed_domains: list[str] | None = None,
        filter_static: bool = True,
    ):
        self.session_id = session_id
        self.event_consumer = event_consumer
        self.allowed_domains = allowed_domains
        self.filter_static = filter_static
        self.sequence = 0
        self._request_map: dict[str, str] = {}  # pw_request -> event_id
        self._filtered_requests: set[str] = set()

    def _should_filter_request(self, request: PWRequest) -> bool:
        if not self.filter_static:
            return False

        # 1. Resource type filter
        if request.resource_type in STATIC_RESOURCE_TYPES:
            return True

        url = request.url.lower()
        parsed = urlparse(url)

        # 2. Extension filter
        path = parsed.path
        if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
            return True

        # 3. Analytics / Tracking filter
        netloc = parsed.netloc
        if any(domain in netloc for domain in TRACKING_DOMAINS):
            return True

        # 4. Scope limiting by allowed_domains (if specified)
        if self.allowed_domains:
            if not any(d in netloc for d in self.allowed_domains):
                return True

        return False

    def _req_key(self, request: PWRequest) -> str:
        impl = getattr(request, "_impl_obj", None)
        if impl and hasattr(impl, "_guid") and impl._guid:
            return str(impl._guid)
        guid = getattr(request, "_guid", None)
        if guid:
            return str(guid)
        return str(id(request))

    async def on_request(self, request: PWRequest, page_id: str | None = None) -> None:
        req_key = self._req_key(request)
        if self._should_filter_request(request):
            self._filtered_requests.add(req_key)
            return

        self.sequence += 1
        # Trích xuất ngay x-lineage-req-id từ sync headers và lưu map trước mọi lệnh await
        sync_headers = request.headers
        lineage_req_id = sync_headers.get("x-lineage-req-id")
        event_id = lineage_req_id or f"evt_req_{uuid.uuid4().hex[:10]}"
        self._request_map[req_key] = event_id

        headers = await request.all_headers()
        if not lineage_req_id and "x-lineage-req-id" in headers:
            lineage_req_id = headers["x-lineage-req-id"]
            event_id = lineage_req_id
            self._request_map[req_key] = event_id

        parsed = urlparse(request.url)
        query_dict = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}

        frame_id = None
        if request.frame:
            frame_id = getattr(request.frame, "_guid", None) or str(id(request.frame))

        payload = {
            "transport": "playwright_network",
            "request_id": event_id,
            "method": request.method,
            "url": request.url,
            "host": parsed.netloc,
            "path": parsed.path,
            "query": query_dict,
            "headers": headers,
            "resource_type": request.resource_type,
            "post_data": request.post_data,
        }

        envelope = EventEnvelope(
            event_id=event_id,
            schema_version=1,
            session_id=self.session_id,
            source="browser",
            event_type=EventType.NETWORK_REQUEST,
            timestamp_ns=time.time_ns(),
            sequence=self.sequence,
            page_id=page_id,
            frame_id=frame_id,
            payload=payload,
            metadata={"is_navigation_request": request.is_navigation_request()},
        )

        res = self.event_consumer(envelope)
        if hasattr(res, "__await__"):
            await res

    async def on_response(self, response: PWResponse, page_id: str | None = None) -> None:
        req_key = self._req_key(response.request)
        if req_key in self._filtered_requests:
            self._filtered_requests.discard(req_key)
            return

        self.sequence += 1
        req_event_id = self._request_map.get(req_key)
        if not req_event_id:
            req_event_id = response.request.headers.get("x-lineage-req-id")
        if not req_event_id:
            req_event_id = f"req_{uuid.uuid4().hex[:10]}"
        event_id = f"evt_res_{uuid.uuid4().hex[:10]}"

        body_preview = None
        body_size = 0
        try:
            # Chỉ lấy preview body cho text/json để tối ưu bộ nhớ
            content_type = response.headers.get("content-type", "").lower()
            if any(t in content_type for t in ["json", "text", "javascript", "xml", "html"]):
                body_bytes = await response.body()
                body_size = len(body_bytes)
                body_preview = body_bytes[:65536].decode("utf-8", errors="replace")
        except Exception:
            pass

        frame_id = None
        if response.frame:
            frame_id = getattr(response.frame, "_guid", None) or str(id(response.frame))

        payload = {
            "transport": "playwright_network",
            "request_id": req_event_id,
            "url": response.url,
            "status_code": response.status,
            "headers": await response.all_headers(),
            "body": body_preview,
            "body_size": body_size,
        }

        envelope = EventEnvelope(
            event_id=event_id,
            schema_version=1,
            session_id=self.session_id,
            source="browser",
            event_type=EventType.NETWORK_RESPONSE,
            timestamp_ns=time.time_ns(),
            sequence=self.sequence,
            page_id=page_id,
            frame_id=frame_id,
            payload=payload,
            metadata={"status_text": response.status_text},
        )

        res = self.event_consumer(envelope)
        if hasattr(res, "__await__"):
            await res
