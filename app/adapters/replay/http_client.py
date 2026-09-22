import json
import time
from typing import Any
import httpx

from app.domain.replay.entities import ReplayExecutionResult, ReplayRequest
from app.domain.replay.policies import ReplaySafetyPolicy
from app.ports.replay import HTTPReplayExecutorPort


class HttpxReplayExecutor(HTTPReplayExecutorPort):
    """Adapter thực thi HTTP request sử dụng httpx.AsyncClient."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    async def execute(
        self,
        request: ReplayRequest,
        policy: ReplaySafetyPolicy | None = None,
    ) -> ReplayExecutionResult:
        pol = policy or ReplaySafetyPolicy()

        # 1. Kiểm tra an toàn trước khi gửi
        if not pol.is_url_allowed(request.url):
            return ReplayExecutionResult(
                request_id="blocked",
                status_code=403,
                success=False,
                error_message=f"URL '{request.url}' violates safety policy (host not allowed)",
            )

        if not pol.is_method_allowed(request.method):
            return ReplayExecutionResult(
                request_id="blocked",
                status_code=405,
                success=False,
                error_message=f"HTTP Method '{request.method}' is not allowed by policy",
            )

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=request.timeout_seconds,
                follow_redirects=True,
                cookies=request.cookies,
            ) as client:
                # Chuẩn bị payload
                content = None
                json_data = None
                if request.body is not None:
                    if isinstance(request.body, (dict, list)):
                        json_data = request.body
                    elif isinstance(request.body, str):
                        try:
                            json_data = json.loads(request.body)
                        except Exception:
                            content = request.body.encode("utf-8")
                    else:
                        content = str(request.body).encode("utf-8")

                resp = await client.request(
                    method=request.method,
                    url=request.url,
                    headers=request.headers,
                    params=request.query,
                    json=json_data,
                    content=content,
                )

                latency_ms = (time.perf_counter() - start_time) * 1000

                # Đọc body phản hồi
                resp_body: Any = None
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = resp.text

                return ReplayExecutionResult(
                    request_id=f"rep_{int(time.time()*1000)}",
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    body=resp_body,
                    latency_ms=round(latency_ms, 2),
                    success=(200 <= resp.status_code < 400),
                )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ReplayExecutionResult(
                request_id="error",
                status_code=500,
                latency_ms=round(latency_ms, 2),
                success=False,
                error_message=str(exc),
            )
