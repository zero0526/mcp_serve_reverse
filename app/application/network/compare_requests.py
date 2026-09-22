from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.application.network.summarize_request import SummarizeRequestUseCase


class CompareRequestsUseCase:
    """Use case so sánh hai HTTP Request để chỉ ra các điểm tương đồng và dị biệt."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.summarize_use_case = SummarizeRequestUseCase(session_factory)

    async def execute(
        self,
        left_session_id: str,
        left_request_id: str,
        right_session_id: str,
        right_request_id: str,
        redaction_mode: str = "strict",
    ) -> dict[str, Any]:
        left = await self.summarize_use_case.execute(
            session_id=left_session_id,
            request_id=left_request_id,
            redaction_mode=redaction_mode,
        )
        right = await self.summarize_use_case.execute(
            session_id=right_session_id,
            request_id=right_request_id,
            redaction_mode=redaction_mode,
        )

        if not left or not right:
            return {
                "status": "NOT_FOUND",
                "left_found": left is not None,
                "right_found": right is not None,
            }

        differences = []
        if left["method"] != right["method"]:
            differences.append(f"Method khác nhau: {left['method']} vs {right['method']}")
        if left["url"] != right["url"]:
            differences.append(f"URL khác nhau: {left['url']} vs {right['url']}")

        # Compare headers keys
        left_headers = set(left.get("headers", {}).keys())
        right_headers = set(right.get("headers", {}).keys())
        headers_only_left = list(left_headers - right_headers)
        headers_only_right = list(right_headers - left_headers)
        if headers_only_left:
            differences.append(f"Headers chỉ có ở bên trái: {headers_only_left}")
        if headers_only_right:
            differences.append(f"Headers chỉ có ở bên phải: {headers_only_right}")

        # Compare query keys
        left_query = set(left.get("query", {}).keys())
        right_query = set(right.get("query", {}).keys())
        query_only_left = list(left_query - right_query)
        query_only_right = list(right_query - left_query)
        if query_only_left:
            differences.append(f"Query params chỉ có ở bên trái: {query_only_left}")
        if query_only_right:
            differences.append(f"Query params chỉ có ở bên phải: {query_only_right}")

        # Compare body keys (nếu là dict)
        left_body = left.get("body")
        right_body = right.get("body")
        if isinstance(left_body, dict) and isinstance(right_body, dict):
            body_only_left = list(set(left_body.keys()) - set(right_body.keys()))
            body_only_right = list(set(right_body.keys()) - set(left_body.keys()))
            if body_only_left:
                differences.append(f"Body keys chỉ có ở bên trái: {body_only_left}")
            if body_only_right:
                differences.append(f"Body keys chỉ có ở bên phải: {body_only_right}")
        elif left_body != right_body:
            differences.append("Nội dung body payload khác nhau")

        return {
            "is_identical": len(differences) == 0,
            "differences": differences,
            "left_request": {
                "id": left["id"],
                "method": left["method"],
                "url": left["url"],
            },
            "right_request": {
                "id": right["id"],
                "method": right["method"],
                "url": right["url"],
            },
        }
