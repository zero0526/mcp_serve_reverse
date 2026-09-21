import time
import uuid
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Request as PWRequest, Response as PWResponse

from app.domain.trace.events import EventType
from app.domain.trace.value_objects import EventEnvelope


class NetworkMapper:
    """Mapper lắng nghe sự kiện mạng tầng Playwright và đóng gói thành EventEnvelope."""

    def __init__(
        self,
        session_id: str,
        event_consumer: Callable[[EventEnvelope], Any],
    ):
        self.session_id = session_id
        self.event_consumer = event_consumer
        self.sequence = 0
        self._request_map: dict[str, str] = {}  # pw_request -> event_id

    async def on_request(self, request: PWRequest) -> None:
        self.sequence += 1
        event_id = f"evt_req_{uuid.uuid4().hex[:10]}"
        self._request_map[str(id(request))] = event_id

        parsed = urlparse(request.url)
        query_dict = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}

        payload = {
            "transport": "playwright_network",
            "request_id": event_id,
            "method": request.method,
            "url": request.url,
            "host": parsed.netloc,
            "path": parsed.path,
            "query": query_dict,
            "headers": await request.all_headers(),
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
            payload=payload,
            metadata={"is_navigation_request": request.is_navigation_request()},
        )

        res = self.event_consumer(envelope)
        if hasattr(res, "__await__"):
            await res

    async def on_response(self, response: PWResponse) -> None:
        self.sequence += 1
        req_id_key = str(id(response.request))
        req_event_id = self._request_map.get(req_id_key, f"req_{uuid.uuid4().hex[:10]}")
        event_id = f"evt_res_{uuid.uuid4().hex[:10]}"

        body_preview = None
        body_size = 0
        try:
            # Chỉ lấy preview body cho text/json để tối ưu bộ nhớ
            content_type = response.headers.get("content-type", "").lower()
            if any(t in content_type for t in ["json", "text", "javascript", "xml", "html"]):
                body_bytes = await response.body()
                body_size = len(body_bytes)
                body_preview = body_bytes[:4096].decode("utf-8", errors="replace")
        except Exception:
            pass

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
            payload=payload,
            metadata={"status_text": response.status_text},
        )

        res = self.event_consumer(envelope)
        if hasattr(res, "__await__"):
            await res
