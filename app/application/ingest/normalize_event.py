import hashlib
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.domain.trace.value_objects import EventEnvelope
from app.infrastructure.serialization.json import safe_dumps


class EventNormalizer:
    """Chuẩn hóa dữ liệu sự kiện (URL, headers, payload hash)."""

    def normalize(self, event: EventEnvelope) -> dict[str, Any]:
        payload = event.payload.copy()
        normalized: dict[str, Any] = {
            "event_type": str(event.event_type),
            "payload": payload,
        }

        # Tính hash của payload để phục vụ deduplication và truy vết
        payload_str = safe_dumps(payload)
        payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        normalized["payload_hash"] = payload_hash

        # Chuẩn hóa URL và Query nếu có
        url = payload.get("url")
        if url and isinstance(url, str):
            try:
                parsed = urlparse(url)
                normalized["url_parsed"] = {
                    "scheme": parsed.scheme,
                    "host": parsed.netloc,
                    "path": parsed.path,
                    "query": {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()},
                }
            except Exception:
                pass

        # Chuẩn hóa headers thành lowercase keys
        headers = payload.get("headers")
        if isinstance(headers, dict):
            normalized["headers_normalized"] = {
                str(k).lower(): str(v) for k, v in headers.items()
            }

        return normalized


event_normalizer = EventNormalizer()
