import json
from typing import Any
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.graph.stack_parser import parse_v8_stack
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.models import (
    FunctionExecutionModel,
    NetworkRequestModel,
    TraceEventModel,
)
from app.infrastructure.serialization.json import safe_loads
from app.infrastructure.serialization.redaction import redaction_engine
from app.ports.graph_repository import GraphRepositoryPort


class GetExecutionContextUseCase:
    """Use case truy xuất toàn bộ ngữ cảnh thực thi của một hàm (Execution Context).

    Cung cấp:
    - Thông tin hàm: function_name, module_name, source_location, timestamps, status.
    - Cây gọi hàm: caller (parent) và callees (children).
    - Arguments và Return value (đã được áp dụng chính sách bảo mật redaction).
    - Call stack V8 đã phân tách thành các frame có cấu trúc.
    - Các HTTP request lân cận hoặc trực tiếp do hàm kích hoạt.
    - Các sự kiện vết lân cận theo dòng thời gian.
    """

    def __init__(
        self,
        session_factory=AsyncSessionLocal,
        graph_repo: GraphRepositoryPort | None = None,
    ):
        self.session_factory = session_factory
        self.graph_repo = graph_repo

    async def execute(
        self,
        session_id: str,
        execution_id: str,
        include_arguments: bool = True,
        include_return_value: bool = True,
        include_stack_trace: bool = True,
        include_related_network: bool = True,
        include_call_tree: bool = True,
        max_related_events: int = 30,
        time_window_ms: int = 500,
    ) -> dict[str, Any]:
        window_ns = time_window_ms * 1_000_000

        async with self.session_factory() as db:  # type: AsyncSession
            # 1. Tìm bản ghi thực thi chính từ FunctionExecutionModel
            fn_stmt = select(FunctionExecutionModel).where(
                FunctionExecutionModel.session_id == session_id,
                FunctionExecutionModel.id == execution_id,
            )
            fn_row = (await db.execute(fn_stmt)).scalar_one_or_none()

            # 2. Tìm các sự kiện liên quan trực tiếp đến execution_id từ TraceEventModel
            evt_stmt = (
                select(TraceEventModel)
                .where(
                    TraceEventModel.session_id == session_id,
                    TraceEventModel.execution_id == execution_id,
                )
                .order_by(TraceEventModel.timestamp_ns.asc())
            )
            direct_events = (await db.execute(evt_stmt)).scalars().all()

            if not fn_row and not direct_events:
                return {
                    "session_id": session_id,
                    "execution_id": execution_id,
                    "found": False,
                    "error": f"Execution ID '{execution_id}' not found in session '{session_id}'",
                }

            # Trích xuất metadata cơ bản của execution
            function_name = fn_row.function_name if fn_row else None
            module_name = fn_row.module_name if fn_row else None
            source_loc_str = fn_row.source_location if fn_row else None
            parent_exec_id = fn_row.parent_execution_id if fn_row else None
            started_at_ns = fn_row.started_at_ns if fn_row else (direct_events[0].timestamp_ns if direct_events else 0)
            ended_at_ns = fn_row.ended_at_ns if fn_row else (direct_events[-1].timestamp_ns if direct_events else started_at_ns)
            status = fn_row.status if fn_row else "completed"
            raw_stack = fn_row.stack_trace if fn_row else None

            # Bổ sung từ TraceEventModel nếu FunctionExecutionModel còn thiếu
            for evt in direct_events:
                payload = safe_loads(evt.payload_json) if evt.payload_json else {}
                meta = safe_loads(evt.metadata_json) if evt.metadata_json else {}

                if not function_name:
                    function_name = payload.get("function_name") or meta.get("function_name")
                if not parent_exec_id:
                    parent_exec_id = evt.parent_execution_id or payload.get("parent_execution_id")
                if not raw_stack:
                    raw_stack = meta.get("stack") or payload.get("stack") or meta.get("stack_trace")
                if not source_loc_str and (payload.get("file") or meta.get("file")):
                    file_p = payload.get("file") or meta.get("file")
                    line_p = payload.get("line") or meta.get("line")
                    source_loc_str = f"{file_p}:{line_p}" if line_p else str(file_p)

            # Phân tách source location
            source_location = None
            if source_loc_str:
                parts = source_loc_str.split(":")
                file_name = parts[0]
                line_no = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                col_no = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                source_location = {"file": file_name, "line": line_no, "column": col_no}

            # 3. Cây gọi hàm: Caller (Parent) và Callees (Children)
            caller_info = None
            callees_list: list[dict[str, Any]] = []

            if include_call_tree:
                # A. Caller (Parent)
                if parent_exec_id:
                    parent_fn_stmt = select(FunctionExecutionModel).where(
                        FunctionExecutionModel.session_id == session_id,
                        FunctionExecutionModel.id == parent_exec_id,
                    )
                    parent_fn_row = (await db.execute(parent_fn_stmt)).scalar_one_or_none()
                    if parent_fn_row:
                        caller_info = {
                            "execution_id": parent_fn_row.id,
                            "function_name": parent_fn_row.function_name,
                            "module_name": parent_fn_row.module_name,
                            "source_location": parent_fn_row.source_location,
                            "started_at_ns": parent_fn_row.started_at_ns,
                        }
                    else:
                        # Fallback tìm qua TraceEventModel
                        p_evt_stmt = select(TraceEventModel).where(
                            TraceEventModel.session_id == session_id,
                            TraceEventModel.execution_id == parent_exec_id,
                        ).limit(1)
                        p_evt = (await db.execute(p_evt_stmt)).scalar_one_or_none()
                        if p_evt:
                            p_payload = safe_loads(p_evt.payload_json) if p_evt.payload_json else {}
                            caller_info = {
                                "execution_id": parent_exec_id,
                                "function_name": p_payload.get("function_name", "unknown_parent"),
                                "started_at_ns": p_evt.timestamp_ns,
                            }
                        else:
                            caller_info = {"execution_id": parent_exec_id, "function_name": "unknown_parent"}

                # B. Callees (Children)
                callee_fn_stmt = select(FunctionExecutionModel).where(
                    FunctionExecutionModel.session_id == session_id,
                    FunctionExecutionModel.parent_execution_id == execution_id,
                ).order_by(FunctionExecutionModel.started_at_ns.asc())
                callee_fn_rows = (await db.execute(callee_fn_stmt)).scalars().all()

                seen_callee_ids = set()
                for c in callee_fn_rows:
                    seen_callee_ids.add(c.id)
                    callees_list.append({
                        "execution_id": c.id,
                        "function_name": c.function_name,
                        "module_name": c.module_name,
                        "source_location": c.source_location,
                        "started_at_ns": c.started_at_ns,
                        "status": c.status,
                    })

                # Tìm thêm callees từ TraceEventModel
                callee_evt_stmt = select(TraceEventModel).where(
                    TraceEventModel.session_id == session_id,
                    TraceEventModel.parent_execution_id == execution_id,
                ).order_by(TraceEventModel.timestamp_ns.asc())
                callee_evts = (await db.execute(callee_evt_stmt)).scalars().all()

                for ce in callee_evts:
                    cid = ce.execution_id or f"evt_{ce.event_id}"
                    if cid not in seen_callee_ids:
                        seen_callee_ids.add(cid)
                        c_pay = safe_loads(ce.payload_json) if ce.payload_json else {}
                        callees_list.append({
                            "execution_id": cid,
                            "function_name": c_pay.get("function_name") or ce.event_type,
                            "started_at_ns": ce.timestamp_ns,
                            "status": "completed",
                        })

            # 4. Arguments & Return Value (với Redaction)
            arguments_data: list[dict[str, Any]] = []
            return_val_data: dict[str, Any] | None = None

            if include_arguments:
                raw_args = None
                if fn_row and fn_row.arguments_json:
                    raw_args = safe_loads(fn_row.arguments_json)
                if not raw_args:
                    for evt in direct_events:
                        p = safe_loads(evt.payload_json) if evt.payload_json else {}
                        if "arguments" in p or "args" in p:
                            raw_args = p.get("arguments") or p.get("args")
                            break

                if isinstance(raw_args, list):
                    for idx, arg in enumerate(raw_args):
                        redacted = False
                        arg_val = arg
                        if isinstance(arg, dict):
                            redacted_dict = redaction_engine.redact_dict(arg)
                            redacted = redacted_dict != arg
                            arg_val = redacted_dict
                        elif isinstance(arg, str):
                            # Kiểm tra nếu giá trị là jwt/secret/token/password
                            if any(k in arg.lower() for k in ["bearer ", "eyj", "token", "secret", "password", "auth"]):
                                arg_val = redaction_engine.mask_value(arg)
                                redacted = True

                        arguments_data.append({
                            "index": idx,
                            "type": type(arg).__name__,
                            "value": arg_val,
                            "redacted": redacted,
                        })
                elif raw_args is not None:
                    arguments_data.append({
                        "index": 0,
                        "type": type(raw_args).__name__,
                        "value": raw_args,
                        "redacted": False,
                    })

            if include_return_value:
                raw_ret = None
                if fn_row and fn_row.return_value_ref:
                    raw_ret = fn_row.return_value_ref
                if not raw_ret:
                    for evt in direct_events:
                        p = safe_loads(evt.payload_json) if evt.payload_json else {}
                        if "return_value" in p or "result" in p or "output" in p:
                            raw_ret = p.get("return_value") or p.get("result") or p.get("output")
                            break

                if raw_ret is not None:
                    ret_val = raw_ret
                    redacted = False
                    if isinstance(raw_ret, dict):
                        redacted_dict = redaction_engine.redact_dict(raw_ret)
                        redacted = redacted_dict != raw_ret
                        ret_val = redacted_dict
                    elif isinstance(raw_ret, str) and any(k in raw_ret.lower() for k in ["bearer ", "eyj", "token", "secret"]):
                        ret_val = redaction_engine.mask_value(raw_ret)
                        redacted = True

                    return_val_data = {
                        "type": type(raw_ret).__name__,
                        "value": ret_val,
                        "redacted": redacted,
                    }

            # 5. Phân tách Stack Trace V8
            parsed_stack_frames: list[dict[str, Any]] = []
            if include_stack_trace and raw_stack:
                frames = parse_v8_stack(raw_stack)
                parsed_stack_frames = [
                    {
                        "function_name": f.function_name,
                        "file_url": f.file_url,
                        "line_no": f.line_no,
                        "col_no": f.col_no,
                        "raw_frame": f.raw_frame,
                    }
                    for f in frames
                ]

            # 6. Related Network Requests
            related_requests: list[dict[str, Any]] = []
            if include_related_network:
                # A. Requests trực tiếp kích hoạt bởi execution_id
                direct_req_stmt = select(NetworkRequestModel).where(
                    NetworkRequestModel.session_id == session_id,
                    NetworkRequestModel.execution_id == execution_id,
                ).order_by(NetworkRequestModel.started_at_ns.asc())
                direct_reqs = (await db.execute(direct_req_stmt)).scalars().all()

                # B. Requests lân cận theo cửa sổ thời gian
                time_req_stmt = select(NetworkRequestModel).where(
                    NetworkRequestModel.session_id == session_id,
                    NetworkRequestModel.started_at_ns >= (started_at_ns - window_ns),
                    NetworkRequestModel.started_at_ns <= ((ended_at_ns or started_at_ns) + window_ns),
                ).order_by(NetworkRequestModel.started_at_ns.asc())
                time_reqs = (await db.execute(time_req_stmt)).scalars().all()

                seen_req_ids = set()
                for r in list(direct_reqs) + list(time_reqs):
                    if r.id not in seen_req_ids:
                        seen_req_ids.add(r.id)
                        related_requests.append({
                            "request_id": r.id,
                            "method": r.method,
                            "url": r.url,
                            "status": r.status,
                            "started_at_ns": r.started_at_ns,
                            "directly_triggered": r.execution_id == execution_id,
                        })

            # 7. Related / Nearby Events
            related_events: list[dict[str, Any]] = []
            if max_related_events > 0:
                nearby_stmt = (
                    select(TraceEventModel)
                    .where(
                        TraceEventModel.session_id == session_id,
                        TraceEventModel.timestamp_ns >= (started_at_ns - window_ns),
                        TraceEventModel.timestamp_ns <= ((ended_at_ns or started_at_ns) + window_ns),
                    )
                    .order_by(TraceEventModel.timestamp_ns.asc(), TraceEventModel.sequence.asc())
                    .limit(max_related_events)
                )
                nearby_rows = (await db.execute(nearby_stmt)).scalars().all()
                for ne in nearby_rows:
                    ne_pay = safe_loads(ne.payload_json) if ne.payload_json else {}
                    related_events.append({
                        "event_id": ne.event_id,
                        "event_type": ne.event_type,
                        "timestamp_ns": ne.timestamp_ns,
                        "execution_id": ne.execution_id,
                        "summary": ne_pay.get("function_name") or ne_pay.get("url") or ne.event_type,
                    })

            return {
                "session_id": session_id,
                "found": True,
                "execution": {
                    "execution_id": execution_id,
                    "function_name": function_name or "anonymous",
                    "module_name": module_name or "app.js",
                    "source_location": source_location,
                    "parent_execution_id": parent_exec_id,
                    "started_at_ns": started_at_ns,
                    "ended_at_ns": ended_at_ns,
                    "duration_ms": round((ended_at_ns - started_at_ns) / 1_000_000, 3) if ended_at_ns and started_at_ns else 0.0,
                    "status": status,
                },
                "call_tree": {
                    "caller": caller_info,
                    "callees": callees_list,
                    "callees_count": len(callees_list),
                },
                "arguments": arguments_data,
                "return_value": return_val_data,
                "stack_trace": parsed_stack_frames,
                "related_requests": related_requests,
                "related_events": related_events,
            }
