import json
import re
from typing import Any
from urllib.parse import unquote
from sqlalchemy import or_, select

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.models import NetworkRequestModel, NetworkResponseModel
from app.application.network.analyze_request_lineage import AnalyzeRequestLineageUseCase
from app.application.network.compare_requests import CompareRequestsUseCase
from app.application.network.find_request_dependencies import FindRequestDependenciesUseCase
from app.application.network.summarize_request import SummarizeRequestUseCase
from app.infrastructure.storage.blob_storage import default_blob_storage
from app.interfaces.mcp.schemas.responses import create_mcp_response

_graph_repo = SQLiteGraphRepository(session_factory=AsyncSessionLocal)
_summarize_uc = SummarizeRequestUseCase(session_factory=AsyncSessionLocal)
_analyze_req_uc = AnalyzeRequestLineageUseCase(graph_repo=_graph_repo)
_find_dep_uc = FindRequestDependenciesUseCase(graph_repo=_graph_repo)
_compare_req_uc = CompareRequestsUseCase(session_factory=AsyncSessionLocal)


def _extract_friendly_name(headers_str: str | None, body_str: str | None) -> str | None:
    """Trích xuất tên gợi nhớ (friendly_name / operationName) từ headers hoặc request body."""
    if headers_str:
        try:
            h = json.loads(headers_str)
            if isinstance(h, dict):
                for k, v in h.items():
                    if k.lower() in ("x-fb-friendly-name", "x-operation-name", "operation-name"):
                        return str(v)
        except Exception:
            pass
    if body_str:
        # Check form-urlencoded: fb_api_req_friendly_name=... hoặc operationName=...
        m = re.search(r"(?:^|&)(?:fb_api_req_friendly_name|operationName)=([^&]+)", body_str)
        if m:
            return unquote(m.group(1))
        # Check json body: {"operationName": "..."} hoặc {"fb_api_req_friendly_name": "..."}
        try:
            b = json.loads(body_str)
            if isinstance(b, dict):
                return b.get("operationName") or b.get("fb_api_req_friendly_name")
        except Exception:
            pass
    return None
_summarize_uc = SummarizeRequestUseCase(session_factory=AsyncSessionLocal)
_analyze_req_uc = AnalyzeRequestLineageUseCase(graph_repo=_graph_repo)
_find_dep_uc = FindRequestDependenciesUseCase(graph_repo=_graph_repo)
_compare_req_uc = CompareRequestsUseCase(session_factory=AsyncSessionLocal)


async def summarize_request_tool(
    session_id: str,
    request_id: str,
    include_headers: bool = True,
    include_response: bool = True,
    redaction_mode: str = "strict",
) -> dict[str, Any]:
    """MCP Tool: Tóm tắt HTTP Request, Response và tự động che giấu các thông tin bảo mật."""
    res = await _summarize_uc.execute(
        session_id=session_id,
        request_id=request_id,
        include_headers=include_headers,
        include_response=include_response,
        redaction_mode=redaction_mode,
    )
    if not res:
        return create_mcp_response(
            status="NOT_FOUND",
            data={},
            session_id=session_id,
            warnings=[f"Không tìm thấy request '{request_id}' trong session '{session_id}'."],
            source="network_analysis",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        redaction_mode=redaction_mode,
        source="network_analysis",
    )


async def analyze_request_lineage_tool(
    session_id: str,
    request_id: str,
    min_confidence: float = 0.8,
) -> dict[str, Any]:
    """MCP Tool: Phân tích toàn bộ nguồn gốc của các tham số cấu thành một request cụ thể."""
    res = await _analyze_req_uc.execute(
        session_id=session_id,
        request_id=request_id,
        min_confidence=min_confidence,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=len(res.get("parameters", [])),
        source="network_analysis",
    )


async def find_request_dependencies_tool(
    session_id: str,
    request_id: str,
    include_storage: bool = True,
    include_executions: bool = True,
    max_depth: int = 10,
) -> dict[str, Any]:
    """MCP Tool: Tìm các phụ thuộc (Dependencies) của request: storage, dispatcher, crypto, value."""
    res = await _find_dep_uc.execute(
        session_id=session_id,
        request_id=request_id,
        include_storage=include_storage,
        include_executions=include_executions,
        max_depth=max_depth,
    )
    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        result_count=res.get("total_dependencies", 0),
        source="network_analysis",
    )


async def compare_requests_tool(
    left_session_id: str,
    left_request_id: str,
    right_session_id: str,
    right_request_id: str,
    redaction_mode: str = "strict",
) -> dict[str, Any]:
    """MCP Tool: So sánh hai HTTP Request để tìm ra sự khác biệt về URL, method, headers, payload."""
    res = await _compare_req_uc.execute(
        left_session_id=left_session_id,
        left_request_id=left_request_id,
        right_session_id=right_session_id,
        right_request_id=right_request_id,
        redaction_mode=redaction_mode,
    )
    if res.get("status") == "NOT_FOUND":
        return create_mcp_response(
            status="NOT_FOUND",
            data=res,
            session_id=left_session_id,
            warnings=["Một trong hai request không tồn tại."],
            source="network_analysis",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=left_session_id,
        redaction_mode=redaction_mode,
        source="network_analysis",
    )


async def list_requests_tool(
    session_id: str,
    method: str | None = None,
    url_keyword: str | None = None,
    body_keyword: str | None = None,
    friendly_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """MCP Tool: Liệt kê danh sách các HTTP Requests đã bắt được trong session có lọc theo method, url, body keyword và friendly_name."""
    async with AsyncSessionLocal() as db:
        stmt = select(NetworkRequestModel).where(NetworkRequestModel.session_id == session_id)
        if method:
            stmt = stmt.where(NetworkRequestModel.method == method.upper())
        if url_keyword:
            stmt = stmt.where(NetworkRequestModel.url.ilike(f"%{url_keyword}%"))
        if body_keyword:
            stmt = stmt.where(NetworkRequestModel.body_json.ilike(f"%{body_keyword}%"))
        if friendly_name:
            stmt = stmt.where(
                or_(
                    NetworkRequestModel.headers_json.ilike(f"%{friendly_name}%"),
                    NetworkRequestModel.body_json.ilike(f"%{friendly_name}%"),
                )
            )

        stmt = stmt.order_by(NetworkRequestModel.started_at_ns.asc()).limit(limit).offset(offset)
        requests = (await db.execute(stmt)).scalars().all()

        results = []
        for r in requests:
            resp_stmt = select(NetworkResponseModel.status_code).where(NetworkResponseModel.request_id == r.id)
            status_code = (await db.execute(resp_stmt)).scalar_one_or_none()

            req_fn = _extract_friendly_name(r.headers_json, r.body_json)

            results.append({
                "request_id": r.id,
                "session_id": r.session_id,
                "method": r.method,
                "url": r.url,
                "path": r.path,
                "friendly_name": req_fn,
                "status_code": status_code,
                "has_payload": bool(r.body_json and r.body_json != "{}"),
                "started_at_ns": r.started_at_ns,
            })

    return create_mcp_response(
        status="COMPLETED",
        data={"requests": results, "total_count": len(results)},
        session_id=session_id,
        result_count=len(results),
        source="network_discovery",
    )


async def detect_security_challenges_tool(
    session_id: str,
    request_id: str | None = None,
) -> dict[str, Any]:
    """MCP Tool: Tự động quét và phát hiện các request bị chặn bởi thử thách bảo mật
    (Secured Action, 2FA, Captcha, Checkpoint) và chuỗi request giải quyết thử thách tiếp theo.
    """
    async with AsyncSessionLocal() as db:
        if request_id:
            req_stmt = (
                select(NetworkRequestModel, NetworkResponseModel)
                .join(NetworkResponseModel, NetworkRequestModel.id == NetworkResponseModel.request_id)
                .where(NetworkRequestModel.id == request_id)
            )
            trigger_pairs = (await db.execute(req_stmt)).all()
        else:
            req_stmt = (
                select(NetworkRequestModel, NetworkResponseModel)
                .join(NetworkResponseModel, NetworkRequestModel.id == NetworkResponseModel.request_id)
                .where(NetworkRequestModel.session_id == session_id)
                .where(
                    or_(
                        NetworkResponseModel.status_code.in_([400, 401, 403, 429]),
                        NetworkResponseModel.body_json.ilike("%Secured Action%"),
                        NetworkResponseModel.body_json.ilike("%challenge_type%"),
                        NetworkResponseModel.body_json.ilike("%two_factor%"),
                        NetworkResponseModel.body_json.ilike("%reauth%"),
                        NetworkResponseModel.body_json.ilike("%captcha%"),
                        NetworkResponseModel.body_json.ilike("%checkpoint%"),
                    )
                )
                .order_by(NetworkRequestModel.started_at_ns.asc())
            )
            all_pairs = (await db.execute(req_stmt)).all()
            # Lọc bỏ các static asset file (js, css, ảnh, fonts)
            trigger_pairs = []
            for r, resp in all_pairs:
                url_lower = r.url.lower()
                if any(
                    url_lower.endswith(ext) or f"{ext}?" in url_lower
                    for ext in [".js", ".css", ".png", ".jpg", ".woff", ".svg", ".ico"]
                ):
                    continue
                trigger_pairs.append((r, resp))

        detected_challenges = []

        for req, resp in trigger_pairs:
            resp_body_str = resp.body_json or ""
            resp_data = {}
            try:
                resp_data = json.loads(resp_body_str)
                if isinstance(resp_data, str):
                    resp_data = json.loads(resp_data)
            except Exception:
                resp_data = {}

            errors = resp_data.get("errors") if isinstance(resp_data, dict) else []
            status_code = resp.status_code
            is_challenge = (
                status_code in (401, 403, 429)
                or "Secured Action" in resp_body_str
                or "challenge_type" in resp_body_str
                or (isinstance(errors, list) and len(errors) > 0 and any("challenge" in str(e).lower() or "reauth" in str(e).lower() for e in errors))
            )
            if not is_challenge and not request_id:
                continue

            challenge_type = "unknown"
            encrypted_context = None
            account_id = None
            challenge_summary = "Security Challenge"
            error_code = None

            if isinstance(errors, list) and len(errors) > 0:
                first_err = errors[0] if isinstance(errors[0], dict) else {}
                challenge_summary = first_err.get("summary") or first_err.get("message") or challenge_summary
                error_code = first_err.get("code") or first_err.get("api_error_code")
                desc = first_err.get("description") or ""
                try:
                    desc_obj = json.loads(desc)
                    if isinstance(desc_obj, dict):
                        challenge_type = desc_obj.get("challenge_type") or challenge_type
                        encrypted_context = desc_obj.get("encrypted_context")
                        account_id = desc_obj.get("account_id")
                except Exception:
                    pass

            if not encrypted_context and resp_body_str:
                m_ctx = re.search(r'"encrypted_?context"\s*:\s*"([^"]+)"', resp_body_str, re.IGNORECASE)
                if m_ctx:
                    encrypted_context = m_ctx.group(1)

            if "reauth" in resp_body_str.lower() or "secured action" in resp_body_str.lower():
                if challenge_type == "unknown":
                    challenge_type = "reauth"
            elif "captcha" in resp_body_str.lower() or "turnstile" in resp_body_str.lower():
                challenge_type = "captcha"
            elif "otp" in resp_body_str.lower() or "two_factor" in resp_body_str.lower() or "two_step" in resp_body_str.lower():
                challenge_type = "2fa_otp"

            # 2. Lần vết chuỗi request giải quyết thử thách (Downstream Resolution Chain)
            chain_stmt = (
                select(NetworkRequestModel, NetworkResponseModel)
                .outerjoin(NetworkResponseModel, NetworkRequestModel.id == NetworkResponseModel.request_id)
                .where(NetworkRequestModel.session_id == session_id)
                .where(NetworkRequestModel.started_at_ns > req.started_at_ns)
                .order_by(NetworkRequestModel.started_at_ns.asc())
            )
            subsequent_pairs = (await db.execute(chain_stmt)).all()

            resolution_chain = []
            is_resolved = False
            step_idx = 1
            trigger_fn = _extract_friendly_name(req.headers_json, req.body_json)

            for sub_req, sub_resp in subsequent_pairs:
                sub_body = sub_req.body_json or ""
                sub_fn = _extract_friendly_name(sub_req.headers_json, sub_body)
                sub_resp_body = sub_resp.body_json if sub_resp else ""

                is_related = False
                purpose = "GENERAL_ACTIVITY"

                # Khớp context mã hóa
                if encrypted_context and (encrypted_context[:30] in sub_body or encrypted_context[:30] in sub_req.url):
                    is_related = True

                # Khớp qua từ khóa 2FA/Auth
                fn_lower = (sub_fn or "").lower()
                url_lower = sub_req.url.lower()
                if any(
                    k in fn_lower or k in url_lower or k in sub_body.lower()
                    for k in ["twostep", "twofactor", "validatecode", "sendcode", "verifycode", "reauth", "captcha"]
                ):
                    is_related = True

                # Khớp retry của chính request ban đầu
                is_retry = (
                    sub_req.id != req.id
                    and sub_req.method == req.method
                    and (sub_req.path == req.path or sub_req.url == req.url)
                    and (sub_fn == trigger_fn if sub_fn and trigger_fn else True)
                )
                if is_retry and resolution_chain:
                    is_related = True
                    purpose = "ACTION_RETRY"

                if not is_related:
                    continue

                if "rootquery" in fn_lower or "method" in fn_lower or "config" in fn_lower:
                    purpose = "QUERY_2FA_METHODS"
                elif "sendcode" in fn_lower or "send_notification" in fn_lower or "send_otp" in fn_lower:
                    purpose = "DISPATCH_OTP_CODE"
                elif "validatecode" in fn_lower or "verify" in fn_lower or "submit_captcha" in fn_lower:
                    purpose = "VALIDATE_CHALLENGE_CODE"
                    if (
                        'is_code_valid":true' in sub_resp_body
                        or 'is_valid":true' in sub_resp_body
                        or '"is_success":true' in sub_resp_body
                    ):
                        is_resolved = True
                elif is_retry:
                    purpose = "ACTION_RETRY"
                    if (
                        '"error":null' in sub_resp_body
                        or '"errors":null' in sub_resp_body
                        or (sub_resp and sub_resp.status_code == 200 and "errors" not in sub_resp_body)
                    ):
                        is_resolved = True

                resolution_chain.append({
                    "step": step_idx,
                    "request_id": sub_req.id,
                    "method": sub_req.method,
                    "url": sub_req.url,
                    "friendly_name": sub_fn,
                    "purpose": purpose,
                    "status_code": sub_resp.status_code if sub_resp else None,
                    "has_payload": bool(sub_body and sub_body != "{}"),
                    "started_at_ns": sub_req.started_at_ns,
                })
                step_idx += 1

                if purpose == "ACTION_RETRY" and is_resolved:
                    break

            detected_challenges.append({
                "trigger_request": {
                    "request_id": req.id,
                    "method": req.method,
                    "url": req.url,
                    "path": req.path,
                    "friendly_name": trigger_fn,
                    "status_code": resp.status_code,
                    "started_at_ns": req.started_at_ns,
                },
                "challenge_info": {
                    "summary": challenge_summary,
                    "challenge_type": challenge_type,
                    "error_code": error_code,
                    "encrypted_context_preview": f"{encrypted_context[:30]}..." if encrypted_context else None,
                    "has_encrypted_context": bool(encrypted_context),
                    "account_id": account_id,
                },
                "resolution_chain": resolution_chain,
                "is_resolved": is_resolved,
                "replay_strategy": {
                    "requires_multi_step": len(resolution_chain) > 0,
                    "action_on_challenge": (
                        "Bắt lỗi response thử thách, trích xuất encrypted_context/ticket. "
                        "Thực thi các bước trong resolution_chain để gửi và xác thực mã OTP. "
                        "Sau khi xác thực thành công, session server sẽ được cấp quyền; "
                        "tiến hành gọi lại chính xác request ban đầu (Action Retry) mà không cần đính kèm token mới."
                    ),
                },
            })

    return create_mcp_response(
        status="COMPLETED",
        data={
            "session_id": session_id,
            "challenges_found": len(detected_challenges),
            "challenges": detected_challenges,
        },
        session_id=session_id,
        result_count=len(detected_challenges),
        source="security_challenge_detector",
    )


async def get_blob_content_tool(
    session_id: str,
    blob_id: str | None = None,
    file_path: str | None = None,
    format: str = "summary",
    offset: int = 0,
    max_bytes: int = 4096,
) -> dict[str, Any]:
    """MCP Tool: Đọc và trích xuất nội dung của file media/blob (video, ảnh, binary, base64) đã được cách ly ra thư mục data/blobs.

    Tham số:
    - session_id: ID của phiên capture
    - blob_id: ID định danh của blob (ví dụ: blob_7a8b9c1d...)
    - file_path: Đường dẫn file trực tiếp trên đĩa (nếu lấy từ $blob_ref)
    - format: Định dạng muốn lấy:
      * "summary" (mặc định): Trả về metadata (kích thước, MIME type, sha256, đường dẫn, hex preview 64 bytes)
      * "path": Lấy absolute file path để truyền cho script upload file multipart trong Python
      * "base64": Lấy chuỗi base64 (hỗ trợ phân đoạn offset và max_bytes để kéo an toàn)
      * "text": Đọc nội dung dưới dạng text UTF-8
    - offset: Vị trí byte bắt đầu đọc (dùng khi đọc file lớn theo chunk)
    - max_bytes: Số byte tối đa đọc trong 1 lần gọi (mặc định 4096 bytes để bảo vệ Context Token của Agent)
    """
    res = default_blob_storage.read_blob_content(
        session_id=session_id,
        blob_id=blob_id,
        file_path=file_path,
        format=format,
        offset=offset,
        max_bytes=max_bytes,
    )
    if res.get("status") == "NOT_FOUND":
        return create_mcp_response(
            status="NOT_FOUND",
            data=res,
            session_id=session_id,
            warnings=[res.get("message", "Blob not found.")],
            source="blob_storage",
        )

    return create_mcp_response(
        status="COMPLETED",
        data=res,
        session_id=session_id,
        source="blob_storage",
    )

