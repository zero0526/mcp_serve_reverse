import json
import time
import uuid
from typing import Any, Callable

from app.domain.trace.value_objects import EventEnvelope


class JSBridge:
    """Cầu nối nhận sự kiện từ JavaScript in-page chuyển thành EventEnvelope."""

    def __init__(
        self,
        session_id: str,
        event_consumer: Callable[[EventEnvelope], Any],
    ):
        self.session_id = session_id
        self.event_consumer = event_consumer
        self.sequence = 0

    async def handle_event_dict(
        self,
        data: dict[str, Any],
        page_id: str | None = None,
        frame_id: str | None = None,
    ) -> None:
        """Xử lý trực tiếp event dictionary (từ poll queue hoặc bridge)."""
        self.sequence += 1
        event_type = data.get("event_type", "unknown")
        timestamp_ms = data.get("timestamp_ms", int(time.time() * 1000))
        timestamp_ns = timestamp_ms * 1_000_000

        event_payload = data.get("payload", {})
        metadata = {}
        if data.get("stack"):
            metadata["stack_trace"] = data["stack"]

        envelope = EventEnvelope(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            schema_version=1,
            session_id=self.session_id,
            source="browser",
            event_type=event_type,
            timestamp_ns=timestamp_ns,
            sequence=self.sequence,
            page_id=page_id,
            frame_id=frame_id,
            payload=event_payload,
            metadata=metadata,
        )

        res = self.event_consumer(envelope)
        if hasattr(res, "__await__"):
            await res

    async def handle_bridge_call(self, source: dict[str, Any], payload_str: str) -> None:
        """Handler được bind vào `__api_lineage_bridge__` trên page."""
        try:
            data = json.loads(payload_str)
        except Exception:
            return

        page_id = None
        frame_id = None
        page = getattr(source, "page", None) if not isinstance(source, dict) else source.get("page")
        frame = getattr(source, "frame", None) if not isinstance(source, dict) else source.get("frame")
        if page:
            page_id = getattr(page, "_guid", None) or str(id(page))
        if frame:
            frame_id = getattr(frame, "_guid", None) or str(id(frame))

        await self.handle_event_dict(data, page_id=page_id, frame_id=frame_id)
