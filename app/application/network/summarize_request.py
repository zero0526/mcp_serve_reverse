from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import NetworkRequestModel, NetworkResponseModel
from app.infrastructure.serialization.json import safe_loads
from app.interfaces.mcp.schemas.responses import redact_sensitive_payload


class SummarizeRequestUseCase:
    """Use case tóm tắt chi tiết HTTP Request/Response và tự động che giấu thông tin nhạy cảm."""

    def __init__(self, session_factory=AsyncSessionLocal):
        self.session_factory = session_factory

    async def execute(
        self,
        session_id: str,
        request_id: str,
        include_headers: bool = True,
        include_response: bool = True,
        redaction_mode: str = "strict",
    ) -> dict[str, Any] | None:
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = select(NetworkRequestModel).where(
                NetworkRequestModel.session_id == session_id,
                (NetworkRequestModel.id == request_id) | (NetworkRequestModel.id.like(f"%{request_id}%")),
            )
            req = (await db.execute(stmt)).scalars().first()
            if not req:
                return None

            headers = safe_loads(req.headers_json) if (include_headers and req.headers_json) else {}
            query = safe_loads(req.query_json) if req.query_json else {}
            body = safe_loads(req.body_json) if req.body_json else None

            res_info = None
            if include_response:
                res_stmt = select(NetworkResponseModel).where(
                    NetworkResponseModel.request_id == req.id
                )
                res = (await db.execute(res_stmt)).scalars().first()
                if res:
                    res_headers = safe_loads(res.headers_json) if (include_headers and res.headers_json) else {}
                    res_body = safe_loads(res.body_json) if res.body_json else None
                    res_info = {
                        "status_code": res.status_code,
                        "headers": redact_sensitive_payload(res_headers, mode=redaction_mode),
                        "body": redact_sensitive_payload(res_body, mode=redaction_mode),
                    }

            req_summary = {
                "id": req.id,
                "method": req.method,
                "url": req.url,
                "host": req.host,
                "path": req.path,
                "resource_type": req.resource_type,
                "started_at_ns": req.started_at_ns,
                "query": redact_sensitive_payload(query, mode=redaction_mode),
                "headers": redact_sensitive_payload(headers, mode=redaction_mode),
                "body": redact_sensitive_payload(body, mode=redaction_mode),
                "response": res_info,
            }

            return req_summary
