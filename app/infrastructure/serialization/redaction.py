import hashlib
import re
from typing import Any

SENSITIVE_KEY_PATTERNS = [
    re.compile(r"^authorization$", re.IGNORECASE),
    re.compile(r"^cookie$", re.IGNORECASE),
    re.compile(r"^set-cookie$", re.IGNORECASE),
    re.compile(r"^proxy-authorization$", re.IGNORECASE),
    re.compile(r".*access_token.*", re.IGNORECASE),
    re.compile(r".*refresh_token.*", re.IGNORECASE),
    re.compile(r".*id_token.*", re.IGNORECASE),
    re.compile(r".*password.*", re.IGNORECASE),
    re.compile(r".*client_secret.*", re.IGNORECASE),
    re.compile(r".*api_?key.*", re.IGNORECASE),
    re.compile(r"^xs$", re.IGNORECASE),
    re.compile(r"^c_user$", re.IGNORECASE),
    re.compile(r"^session_?id$", re.IGNORECASE),
]


class RedactionEngine:
    """Tự động che giấu (redact) các dữ liệu nhạy cảm và sinh hash để so sánh."""

    def __init__(self, salt: str = "api_lineage_redaction_salt"):
        self.salt = salt

    def is_sensitive_key(self, key: str) -> bool:
        k = str(key).strip()
        return any(pattern.match(k) for pattern in SENSITIVE_KEY_PATTERNS)

    def mask_value(self, value: Any) -> str:
        val_str = str(value)
        token_hash = hashlib.sha256(f"{val_str}:{self.salt}".encode("utf-8")).hexdigest()[:16]
        return f"[REDACTED:sha256:{token_hash}]"

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Duyệt đệ quy dict và redact các trường nhạy cảm."""
        redacted = {}
        for k, v in data.items():
            if self.is_sensitive_key(k):
                redacted[k] = self.mask_value(v)
            elif isinstance(v, dict):
                redacted[k] = self.redact_dict(v)
            elif isinstance(v, list):
                redacted[k] = [
                    self.redact_dict(item) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                redacted[k] = v
        return redacted

    def redact_payload(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Redact tùy biến theo từng loại event."""
        payload_copy = payload.copy()

        # Redact headers nếu có
        if "headers" in payload_copy and isinstance(payload_copy["headers"], dict):
            payload_copy["headers"] = self.redact_dict(payload_copy["headers"])

        # Redact query nếu có
        if "query" in payload_copy and isinstance(payload_copy["query"], dict):
            payload_copy["query"] = self.redact_dict(payload_copy["query"])

        # Redact storage operation nếu key nhạy cảm
        if event_type in ["storage_write", "storage_read"]:
            key = payload_copy.get("storage_key", "")
            if self.is_sensitive_key(key):
                if "value_preview" in payload_copy and payload_copy["value_preview"]:
                    payload_copy["value_preview"] = self.mask_value(payload_copy["value_preview"])
                if "raw_cookie_preview" in payload_copy and payload_copy["raw_cookie_preview"]:
                    payload_copy["raw_cookie_preview"] = self.mask_value(payload_copy["raw_cookie_preview"])

        return payload_copy


redaction_engine = RedactionEngine()
