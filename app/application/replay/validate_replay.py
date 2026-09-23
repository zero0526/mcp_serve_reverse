import re
from typing import Any
from urllib.parse import urlparse

from app.domain.replay.entities import ReplayRequest
from app.domain.replay.policies import ReplaySafetyPolicy

PLACEHOLDER_REGEX = re.compile(r"\{\{([^}]+)\}\}")


class ValidateReplayUseCase:
    """Use case kiểm tra chính sách an toàn Replay trước khi phát lại request mạng.

    Kiểm tra:
    - Whitelist domain / hosts
    - HTTP method được phép (chặn các phương thức sửa đổi nếu allow_mutation=False)
    - Phát hiện các biến placeholder chưa được thay thế (ví dụ: {{token}}, {{timestamp}})
    - Rà soát các tiêu đề và tham số bất thường
    """

    def __init__(self, default_policy: ReplaySafetyPolicy | None = None):
        self.default_policy = default_policy or ReplaySafetyPolicy()

    def _find_unreplaced_placeholders(self, data: Any) -> list[str]:
        """Đệ quy quét tìm các placeholder chưa được thay thế."""
        found: list[str] = []
        if isinstance(data, str):
            matches = PLACEHOLDER_REGEX.findall(data)
            found.extend(matches)
        elif isinstance(data, dict):
            for k, v in data.items():
                found.extend(self._find_unreplaced_placeholders(k))
                found.extend(self._find_unreplaced_placeholders(v))
        elif isinstance(data, list):
            for item in data:
                found.extend(self._find_unreplaced_placeholders(item))
        return found

    def execute(
        self,
        request: ReplayRequest,
        policy: ReplaySafetyPolicy | None = None,
    ) -> dict[str, Any]:
        p = policy or self.default_policy
        violations: list[str] = []
        warnings: list[str] = []

        # 1. Kiểm tra URL & Host Whitelist
        if not p.is_url_allowed(request.url):
            parsed = urlparse(request.url)
            violations.append(f"Host '{parsed.hostname}' is not in allowed hosts whitelist: {p.allowed_hosts}")

        # 2. Kiểm tra HTTP Method
        method_upper = request.method.upper()
        if not p.is_method_allowed(method_upper):
            violations.append(f"HTTP method '{method_upper}' is not permitted by policy")

        # 3. Kiểm tra Mutation Safety
        if not p.allow_mutation and method_upper in ("POST", "PUT", "PATCH", "DELETE"):
            violations.append(f"State-mutating method '{method_upper}' is blocked (allow_mutation=False)")

        # 4. Kiểm tra Unreplaced Placeholders trong URL, Headers, Query, Body
        unreplaced = set()
        unreplaced.update(self._find_unreplaced_placeholders(request.url))
        unreplaced.update(self._find_unreplaced_placeholders(request.headers))
        unreplaced.update(self._find_unreplaced_placeholders(request.query))
        unreplaced.update(self._find_unreplaced_placeholders(request.body))

        if unreplaced:
            violations.append(f"Request contains unreplaced template placeholders: {sorted(list(unreplaced))}")

        # 5. Cảnh báo các trường hợp nghi vấn
        if not request.headers:
            warnings.append("Request has no headers defined")

        auth_val = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_val and "Bearer [REDACTED" in auth_val:
            violations.append("Authorization header contains redacted placeholder '[REDACTED' that was not substituted with a live credential")

        # 6. Đánh giá mức độ rủi ro (Risk Level)
        if violations:
            risk_level = "BLOCKED"
            is_valid = False
        elif warnings:
            risk_level = "MEDIUM"
            is_valid = True
        else:
            risk_level = "LOW"
            is_valid = True

        return {
            "is_valid": is_valid,
            "risk_level": risk_level,
            "violations": violations,
            "warnings": warnings,
            "inspected_method": request.method,
            "inspected_url": request.url,
        }
