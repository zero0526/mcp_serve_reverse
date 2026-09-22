import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse
from pydantic import BaseModel, Field


class ReplaySafetyPolicy(BaseModel):
    """Chính sách an toàn kiểm soát việc phát lại request."""

    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_methods: list[str] = Field(
        default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
    )
    allow_mutation: bool = True
    max_timeout_seconds: float = 60.0

    def is_url_allowed(self, url: str) -> bool:
        if not self.allowed_hosts:
            return True
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return any(host == allowed or host.endswith("." + allowed) for allowed in self.allowed_hosts)

    def is_method_allowed(self, method: str) -> bool:
        return method.upper() in [m.upper() for m in self.allowed_methods]


class VariableResolver:
    """Bộ giải quyết và thay thế các biến động {{variable}} trong template."""

    @staticmethod
    def resolve_value(var_name: str, user_inputs: dict[str, Any]) -> Any:
        if var_name in user_inputs:
            return user_inputs[var_name]

        v_lower = var_name.lower()
        if "time" in v_lower or "ts" in v_lower:
            return int(time.time() * 1000)
        if "nonce" in v_lower or "uuid" in v_lower:
            return uuid.uuid4().hex
        return f"mock_{var_name}"

    @classmethod
    def substitute(cls, template: Any, variables: dict[str, Any]) -> Any:
        """Đệ quy thay thế các placeholder {{var}} trong template bất kỳ."""
        if template is None:
            return None

        if isinstance(template, str):
            def replacer(match: re.Match) -> str:
                var_name = match.group(1).strip()
                val = cls.resolve_value(var_name, variables)
                return str(val)

            # Nếu chuỗi chỉ đơn thuần là "{{var}}", trả về đúng kiểu dữ liệu nguyên thủy (int, float, bool...)
            exact_match = re.fullmatch(r"\{\{([^}]+)\}\}", template.strip())
            if exact_match:
                return cls.resolve_value(exact_match.group(1).strip(), variables)

            return re.sub(r"\{\{([^}]+)\}\}", replacer, template)

        if isinstance(template, dict):
            return {k: cls.substitute(v, variables) for k, v in template.items()}

        if isinstance(template, list):
            return [cls.substitute(item, variables) for item in template]

        return template
