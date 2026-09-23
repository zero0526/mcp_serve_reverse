"""Context Reduction & Truncation Guard for MCP Server.

Provides payload guard mechanisms to prevent LLM context overflow:
- Truncates oversized request/response bodies and strings.
- Limits array sizes and object depths.
- Sets explicit `truncated: true` flags and diagnostic warnings.
- Integrates sensitive data redaction.
"""

from typing import Any
from app.interfaces.mcp.schemas.responses import redact_sensitive_payload


class TruncationGuard:
    """Bảo vệ và giới hạn kích thước context gửi về cho LLM client qua MCP."""

    def __init__(
        self,
        max_string_len: int = 2000,
        max_body_len: int = 4000,
        max_list_items: int = 50,
        max_depth: int = 6,
    ):
        self.max_string_len = max_string_len
        self.max_body_len = max_body_len
        self.max_list_items = max_list_items
        self.max_depth = max_depth

    def truncate_string(self, text: str, max_len: int | None = None) -> tuple[str, bool]:
        """Cắt ngắn chuỗi văn bản nếu vượt quá độ dài cho phép."""
        limit = max_len or self.max_string_len
        if len(text) <= limit:
            return text, False
        preview = text[:limit]
        omitted = len(text) - limit
        return f"{preview}... [TRUNCATED: omitted {omitted} characters, original size={len(text)} chars]", True

    def truncate_body(self, body: Any, max_len: int | None = None) -> tuple[Any, bool, str | None]:
        """Xử lý cắt ngắn an toàn cho Request / Response body (chuỗi thô hoặc dict)."""
        limit = max_len or self.max_body_len
        if body is None:
            return None, False, None

        if isinstance(body, str):
            if len(body) > limit:
                truncated_text, _ = self.truncate_string(body, max_len=limit)
                warning = f"Body string truncated from {len(body)} chars to {limit} chars."
                return truncated_text, True, warning
            return body, False, None

        # Nếu body là dict hoặc list
        guarded, is_trunc, warnings = self.guard_payload(body, max_string_len=limit, max_items=self.max_list_items)
        warn_msg = warnings[0] if warnings else None
        return guarded, is_trunc, warn_msg

    def guard_payload(
        self,
        data: Any,
        max_string_len: int | None = None,
        max_items: int | None = None,
        max_depth: int | None = None,
        current_depth: int = 0,
    ) -> tuple[Any, bool, list[str]]:
        """Duyệt đệ quy dict/list để bảo đảm kích thước an toàn cho LLM."""
        str_limit = max_string_len or self.max_string_len
        item_limit = max_items or self.max_list_items
        depth_limit = max_depth or self.max_depth

        truncated = False
        warnings: list[str] = []

        if current_depth > depth_limit:
            return "[TRUNCATED: max object depth reached]", True, ["Max object depth reached."]

        if isinstance(data, str):
            res, was_trunc = self.truncate_string(data, max_len=str_limit)
            if was_trunc:
                truncated = True
                warnings.append(f"String truncated ({len(data)} -> {str_limit} chars)")
            return res, truncated, warnings

        elif isinstance(data, dict):
            res_dict = {}
            for k, v in data.items():
                v_guarded, v_trunc, v_warn = self.guard_payload(
                    v,
                    max_string_len=str_limit,
                    max_items=item_limit,
                    max_depth=depth_limit,
                    current_depth=current_depth + 1,
                )
                res_dict[k] = v_guarded
                if v_trunc:
                    truncated = True
                    warnings.extend(v_warn)
            return res_dict, truncated, warnings

        elif isinstance(data, list):
            res_list = []
            orig_len = len(data)
            sliced = data[:item_limit]
            if orig_len > item_limit:
                truncated = True
                warnings.append(f"List truncated from {orig_len} to {item_limit} items.")

            for item in sliced:
                item_guarded, item_trunc, item_warn = self.guard_payload(
                    item,
                    max_string_len=str_limit,
                    max_items=item_limit,
                    max_depth=depth_limit,
                    current_depth=current_depth + 1,
                )
                res_list.append(item_guarded)
                if item_trunc:
                    truncated = True
                    warnings.extend(item_warn)

            if orig_len > item_limit:
                res_list.append(f"[TRUNCATED: {orig_len - item_limit} more items omitted]")

            return res_list, truncated, warnings

        return data, False, []

    def process_resource_data(
        self,
        data: dict[str, Any],
        redaction_mode: str = "strict",
    ) -> tuple[dict[str, Any], bool, list[str]]:
        """Quy trình hoàn chỉnh: Che giấu thông tin nhạy cảm -> Giới hạn kích thước context."""
        redacted = redact_sensitive_payload(data, mode=redaction_mode)
        guarded, is_truncated, warnings = self.guard_payload(redacted)
        return guarded, is_truncated, warnings


# Singleton instance mặc định
default_truncation_guard = TruncationGuard()
