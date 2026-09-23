import json
import re
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.graph.graph_projector import _flatten_leaves
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    NetworkRequestModel,
    NetworkResponseModel,
)
from app.domain.replay.entities import ReplayRequest
from app.infrastructure.serialization.json import safe_loads
from app.ports.replay import HTTPReplayExecutorPort


class ResolveDependenciesUseCase:
    """Use case tự động phân tích và giải quyết các request phụ thuộc tuần tự.

    Ví dụ: Khi phát lại request 'POST /api/action' có header 'Authorization: Bearer <token>'
    hoặc cookie bắt nguồn từ 'POST /api/login', use case này sẽ:
    1. Xác định request tiền đề sinh ra token/cookie đó.
    2. Lập kế hoạch thực thi tuần tự (Execution Plan).
    3. Trích xuất quy tắc ánh xạ (Extraction Rules) từ response của request trước sang request sau.
    4. (Tùy chọn) Tự động thực thi request tiền đề để lấy token tươi mới.
    """

    def __init__(
        self,
        session_factory=AsyncSessionLocal,
        http_executor: HTTPReplayExecutorPort | None = None,
    ):
        self.session_factory = session_factory
        self.http_executor = http_executor

    async def execute(
        self,
        session_id: str,
        target_request_id: str,
        variables: dict[str, Any] | None = None,
        auto_execute_prerequisites: bool = False,
    ) -> dict[str, Any]:
        vars_dict = dict(variables or {})

        async with self.session_factory() as db:  # type: AsyncSession
            # 1. Tìm target request
            stmt = select(NetworkRequestModel).where(
                NetworkRequestModel.session_id == session_id,
                NetworkRequestModel.id == target_request_id,
            )
            target_req = (await db.execute(stmt)).scalar_one_or_none()

            if not target_req:
                # Fallback tìm kiếm gần đúng
                stmt_fb = select(NetworkRequestModel).where(
                    NetworkRequestModel.session_id == session_id,
                    NetworkRequestModel.id.like(f"%{target_request_id}%"),
                )
                target_req = (await db.execute(stmt_fb)).scalar_one_or_none()

            if not target_req:
                raise ValueError(f"Target request '{target_request_id}' not found in session '{session_id}'")

            # 2. Tìm tất cả các request trước đó trong cùng session
            prev_stmt = (
                select(NetworkRequestModel)
                .where(
                    NetworkRequestModel.session_id == session_id,
                    NetworkRequestModel.started_at_ns < target_req.started_at_ns,
                )
                .order_by(NetworkRequestModel.started_at_ns.asc())
            )
            prev_reqs = (await db.execute(prev_stmt)).scalars().all()

            if not prev_reqs:
                return {
                    "session_id": session_id,
                    "target_request_id": target_req.id,
                    "has_dependencies": False,
                    "dependency_count": 0,
                    "prerequisites": [],
                    "execution_plan": [f"{target_req.method} {target_req.url}"],
                    "resolved_variables": vars_dict,
                }

            # 3. Lấy responses của các request trước
            prev_req_ids = [r.id for r in prev_reqs]
            resp_stmt = select(NetworkResponseModel).where(
                NetworkResponseModel.request_id.in_(prev_req_ids)
            )
            prev_resps = (await db.execute(resp_stmt)).scalars().all()
            resp_map = {r.request_id: r for r in prev_resps}

        # 4. Phân tích đối sánh dữ liệu giữa target request và các response trước
        target_headers = safe_loads(target_req.headers_json) if target_req.headers_json else {}
        target_body = safe_loads(target_req.body_json) if target_req.body_json else None

        prerequisites: list[dict[str, Any]] = []
        step_order = 1

        for pre_req in prev_reqs:
            resp = resp_map.get(pre_req.id)
            if not resp:
                continue

            resp_headers = safe_loads(resp.headers_json) if resp.headers_json else {}
            resp_body = safe_loads(resp.body_json) if resp.body_json else None

            extract_rules: list[dict[str, Any]] = []

            # A. Kiểm tra Set-Cookie -> Cookie
            has_set_cookie = any(k.lower() == "set-cookie" for k in resp_headers.keys())
            has_req_cookie = any(k.lower() == "cookie" for k in target_headers.keys())
            
            for h_name, h_val in resp_headers.items():
                if h_name.lower() == "set-cookie":
                    h_val_str = str(h_val)
                    if "[REDACTED:" not in h_val_str:
                        cookie_parts = h_val_str.split(";")[0].split("=", 1)
                        if len(cookie_parts) == 2:
                            c_name, c_val = cookie_parts[0].strip(), cookie_parts[1].strip()
                            target_cookie_header = str(target_headers.get("cookie", ""))
                            if c_name in target_cookie_header and len(c_val) > 4:
                                extract_rules.append({
                                    "source_type": "response_header",
                                    "source_key": "set-cookie",
                                    "extract_path": f"cookie.{c_name}",
                                    "target_variable": f"cookie_{c_name}",
                                    "inject_into": "headers.cookie",
                                    "matched_value_preview": c_val[:16] + "...",
                                })
                    elif has_req_cookie:
                        extract_rules.append({
                            "source_type": "response_header",
                            "source_key": "set-cookie",
                            "extract_path": "cookie",
                            "target_variable": "session_cookie",
                            "inject_into": "headers.cookie",
                            "matched_value_preview": "[REDACTED_COOKIE]",
                        })

            # B. Kiểm tra Response Body Tokens -> Target Headers (Authorization, x-token, etc.)
            if resp_body:
                leaves = _flatten_leaves(resp_body)
                for path, val in leaves:
                    val_str = str(val).strip()
                    if not val_str or len(val_str) < 6:
                        continue

                    # Kiểm tra xem val_str có xuất hiện trong target headers không (kể cả khi đã bị redact)
                    for th_name, th_val in target_headers.items():
                        th_str = str(th_val)
                        matched = False
                        
                        # 1. Khớp chuỗi thô
                        if val_str in th_str:
                            matched = True
                        # 2. Khớp qua RedactionEngine hash nếu header đã bị che giấu
                        elif "[REDACTED:" in th_str:
                            from app.infrastructure.serialization.redaction import redaction_engine
                            if (
                                redaction_engine.mask_value(val_str) in th_str
                                or redaction_engine.mask_value(f"Bearer {val_str}") in th_str
                                or redaction_engine.mask_value(f"token {val_str}") in th_str
                            ):
                                matched = True
                            # 3. Khớp ngữ nghĩa nếu header là authorization và leaf path có chứa 'token'/'jwt'
                            elif th_name.lower() in ("authorization", "x-access-token", "x-auth-token"):
                                if any(tok_word in path.lower() for tok_word in ("token", "jwt", "auth", "session", "access")):
                                    matched = True

                        if matched:
                            var_name = path.replace(".", "_").replace("[", "_").replace("]", "")
                            vars_dict[var_name] = val_str
                            extract_rules.append({
                                "source_type": "response_body",
                                "source_key": "body",
                                "extract_path": path,
                                "target_variable": var_name,
                                "inject_into": f"headers.{th_name}",
                                "matched_value_preview": val_str[:20] + "...",
                            })

                    # Kiểm tra xem val_str có xuất hiện trong target body không
                    if target_body:
                        target_body_str = json.dumps(target_body) if isinstance(target_body, (dict, list)) else str(target_body)
                        if val_str in target_body_str:
                            var_name = path.replace(".", "_")
                            vars_dict[var_name] = val_str
                            extract_rules.append({
                                "source_type": "response_body",
                                "source_key": "body",
                                "extract_path": path,
                                "target_variable": var_name,
                                "inject_into": "body",
                                "matched_value_preview": val_str[:20] + "...",
                            })

            if extract_rules:
                pre_headers = safe_loads(pre_req.headers_json) if pre_req.headers_json else {}
                pre_body = safe_loads(pre_req.body_json) if pre_req.body_json else None
                prerequisites.append({
                    "order": step_order,
                    "request_id": pre_req.id,
                    "method": pre_req.method,
                    "url": pre_req.url,
                    "headers": pre_headers,
                    "body": pre_body,
                    "extract_rules": extract_rules,
                })
                step_order += 1

        # 5. Nếu auto_execute_prerequisites được bật và có http_executor
        if auto_execute_prerequisites and self.http_executor and prerequisites:
            for p in prerequisites:
                req_obj = ReplayRequest(
                    method=p["method"],
                    url=p["url"],
                    headers=p.get("headers", {}),
                    body=p.get("body"),
                )
                exec_res = await self.http_executor.execute(req_obj)
                if exec_res and exec_res.success:
                    # Trích xuất giá trị thực tế theo extract_rules
                    for rule in p["extract_rules"]:
                        if rule["source_type"] == "response_body" and exec_res.body:
                            leaves = dict(_flatten_leaves(exec_res.body))
                            live_val = leaves.get(rule["extract_path"])
                            if live_val is not None:
                                vars_dict[rule["target_variable"]] = live_val

        execution_plan = [f"{p['method']} {p['url']}" for p in prerequisites] + [f"{target_req.method} {target_req.url}"]

        return {
            "session_id": session_id,
            "target_request_id": target_req.id,
            "has_dependencies": len(prerequisites) > 0,
            "dependency_count": len(prerequisites),
            "prerequisites": prerequisites,
            "execution_plan": execution_plan,
            "resolved_variables": vars_dict,
        }
