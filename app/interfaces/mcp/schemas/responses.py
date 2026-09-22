import time
import uuid
from typing import Any, Literal
from pydantic import BaseModel, Field

StatusType = Literal[
    "COMPLETED",
    "PARTIAL",
    "TRUNCATED",
    "NOT_FOUND",
    "INVALID_INPUT",
    "FORBIDDEN",
    "TIMEOUT",
    "FAILED",
]

RedactionMode = Literal["strict", "standard", "debug"]

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "access_token",
    "refresh_token",
    "id_token",
    "password",
    "client_secret",
    "secret",
}


def redact_sensitive_payload(data: Any, mode: str = "strict") -> Any:
    """Tự động che giấu các thông tin xác thực, token và bí mật trong payload."""
    if mode == "debug":
        return data

    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            is_sensitive = k_lower in SENSITIVE_KEYS or any(
                s in k_lower for s in ["token", "secret", "password", "api_key", "apikey"]
            )
            if is_sensitive and isinstance(v, (str, int, float)):
                v_str = str(v)
                if mode == "strict" or len(v_str) <= 6:
                    redacted[k] = "[REDACTED]"
                else:
                    redacted[k] = f"{v_str[:4]}...[REDACTED]"
            else:
                redacted[k] = redact_sensitive_payload(v, mode=mode)
        return redacted

    elif isinstance(data, list):
        return [redact_sensitive_payload(item, mode=mode) for item in data]

    return data


class MCPResponseEnvelope(BaseModel):
    """Envelope chuẩn hóa cho mọi phản hồi từ MCP Tools theo Phase 4."""

    schema_version: str = "mcp.response.v1"
    request_id: str = Field(default_factory=lambda: f"mcp_req_{uuid.uuid4().hex[:8]}")
    status: StatusType = "COMPLETED"
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


def create_mcp_response(
    status: StatusType = "COMPLETED",
    data: dict[str, Any] | None = None,
    session_id: str | None = None,
    result_count: int | None = None,
    truncated: bool = False,
    warnings: list[str] | None = None,
    redaction_mode: str = "strict",
    source: str = "graph_analysis",
    projection_version: str = "graph-v1",
    analysis_version: str = "lineage-v1",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper xây dựng phản hồi chuẩn Envelope và tự động áp dụng redaction."""
    raw_data = data or {}
    clean_data = redact_sensitive_payload(raw_data, mode=redaction_mode)

    meta = {
        "session_id": session_id,
        "generated_at_ns": time.time_ns(),
        "result_count": result_count if result_count is not None else (len(clean_data) if isinstance(clean_data, (list, dict)) else 1),
        "truncated": truncated,
        "warnings": warnings or [],
    }
    if extra_metadata:
        meta.update(extra_metadata)

    prov = {
        "source": source,
        "projection_version": projection_version,
        "analysis_version": analysis_version,
        "content_origin": "browser_observed",
        "trust_level": "UNTRUSTED_DATA",
    }

    env = MCPResponseEnvelope(
        status=status,
        data=clean_data,
        metadata=meta,
        provenance=prov,
    )
    return env.model_dump()
