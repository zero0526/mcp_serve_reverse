import hashlib
import json
import re
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.adapters.persistence.sqlite.models import (
    NetworkRequestModel,
    TraceEventModel,
)
from app.domain.graph.nodes import NodeType
from app.domain.graph.relations import RelationType
from app.infrastructure.serialization.json import safe_loads
from app.ports.graph_repository import GraphRepositoryPort


TRANSFORMATION_PATTERNS = {
    "serialize": re.compile(r"^(?:JSON\.)?stringify|serialize|qs\.stringify", re.IGNORECASE),
    "deserialize": re.compile(r"^(?:JSON\.)?parse|deserialize|qs\.parse", re.IGNORECASE),
    "hash": re.compile(r"hash|digest|sha\d+|md5|ripemd", re.IGNORECASE),
    "encrypt": re.compile(r"encrypt|cipher|wrapkey", re.IGNORECASE),
    "decrypt": re.compile(r"decrypt|decipher|unwrapkey", re.IGNORECASE),
    "encode": re.compile(r"btoa|encodeURIComponent|encodeURI|base64_?encode|hex|toHex", re.IGNORECASE),
    "decode": re.compile(r"atob|decodeURIComponent|decodeURI|base64_?decode|fromHex", re.IGNORECASE),
    "sign": re.compile(r"sign|hmac", re.IGNORECASE),
    "string": re.compile(r"concat|join|slice|substring|replace|trim", re.IGNORECASE),
}


class FindTransformationsUseCase:
    """Use case phân tích chuỗi các hàm biến đổi dữ liệu liên tiếp (Transformation Pipeline / Chain).

    Ví dụ: raw_string -> JSON.stringify -> crypto.subtle.digest -> base64/hex -> Header/Body.
    """

    def __init__(
        self,
        graph_repository: GraphRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.graph_repo = graph_repository or SQLiteGraphRepository(session_factory)
        self.session_factory = session_factory

    def _classify_function(self, fn_name: str | None) -> tuple[str, str]:
        """Phân loại hàm thành (category, normalized_type)."""
        if not fn_name:
            return "unknown", "unknown"
        fn = fn_name.strip()
        for cat, pat in TRANSFORMATION_PATTERNS.items():
            if pat.search(fn):
                return cat, f"{cat}_{fn.lower()}"
        return "custom", f"func_{fn.lower()}"

    def _extract_source_str(self, source: dict[str, Any] | str | None) -> str | None:
        if not source:
            return None
        if isinstance(source, str):
            return source
        if isinstance(source, dict):
            return (
                source.get("value")
                or source.get("value_hash")
                or source.get("node_id")
                or source.get("param_name")
                or source.get("key")
            )
        return str(source)

    def _extract_target_str(self, target: dict[str, Any] | str | None) -> str | None:
        if not target:
            return None
        if isinstance(target, str):
            return target
        if isinstance(target, dict):
            return (
                target.get("node_id")
                or target.get("request_id")
                or target.get("header")
                or target.get("field")
                or target.get("value")
            )
        return str(target)

    async def execute(
        self,
        session_id: str,
        source: dict[str, Any] | str | None = None,
        target: dict[str, Any] | str | None = None,
        transformation_types: list[str] | None = None,
        direction: str = "both",
        max_depth: int = 10,
        include_arguments: bool = True,
    ) -> dict[str, Any]:
        source_val = self._extract_source_str(source)
        target_val = self._extract_target_str(target)
        types_filter = set(t.lower() for t in transformation_types) if transformation_types else None

        # 1. Truy vấn các Trace Events trong SQLite
        async with self.session_factory() as db:  # type: AsyncSession
            stmt = (
                select(TraceEventModel)
                .where(TraceEventModel.session_id == session_id)
                .order_by(TraceEventModel.timestamp_ns.asc(), TraceEventModel.sequence.asc())
            )
            event_rows = (await db.execute(stmt)).scalars().all()

            # Lấy Network Requests của session để tìm destination sink (Headers / Body)
            req_stmt = (
                select(NetworkRequestModel)
                .where(NetworkRequestModel.session_id == session_id)
                .order_by(NetworkRequestModel.started_at_ns.asc())
            )
            req_rows = (await db.execute(req_stmt)).scalars().all()

        # 2. Quét và trích xuất các bước biến đổi từ events
        extracted_steps: list[dict[str, Any]] = []

        for evt in event_rows:
            etype = evt.event_type
            payload = safe_loads(evt.payload_json) if evt.payload_json else {}

            # A. Crypto Operations (digest, encrypt, decrypt, sign)
            if etype == "crypto_operation":
                op = str(payload.get("operation", "crypto")).lower()
                algo = str(payload.get("algorithm", "")).upper()
                in_val = payload.get("input_preview") or payload.get("input_data") or payload.get("input_hash")
                out_val = payload.get("output_preview") or payload.get("output_data") or payload.get("output_hash")

                cat = "hash" if op in ("digest", "hash") else ("encrypt" if op in ("encrypt", "wrap") else "crypto")
                step_type = f"{cat}_{algo.lower()}" if algo else f"crypto_{op}"

                extracted_steps.append({
                    "event_id": evt.event_id,
                    "execution_id": evt.execution_id,
                    "timestamp_ns": evt.timestamp_ns,
                    "category": cat,
                    "type": step_type,
                    "function_name": f"crypto.subtle.{op}" if op else "crypto.subtle",
                    "algorithm": algo,
                    "input": {"value": in_val, "type": "string" if isinstance(in_val, str) else "bytes"},
                    "output": {"value": out_val, "type": "string" if isinstance(out_val, str) else "bytes"},
                    "confidence": 1.0,
                    "evidence": {
                        "type": "direct_observation",
                        "event_id": evt.event_id,
                        "explanation": f"Web Cryptography API subtle.{op} with {algo}",
                    },
                })

            # B. Serialize / Deserialize
            elif etype in ("serialize", "deserialize"):
                cat = etype
                in_val = payload.get("input") or payload.get("input_preview")
                out_val = payload.get("output") or payload.get("output_preview")
                target_fmt = str(payload.get("target_type", "json")).lower()

                fn_name = "JSON.stringify" if etype == "serialize" and target_fmt == "json" else f"serialize_{target_fmt}"
                if etype == "deserialize":
                    fn_name = "JSON.parse" if target_fmt == "json" else f"deserialize_{target_fmt}"

                extracted_steps.append({
                    "event_id": evt.event_id,
                    "execution_id": evt.execution_id,
                    "timestamp_ns": evt.timestamp_ns,
                    "category": cat,
                    "type": f"{cat}_{target_fmt}",
                    "function_name": fn_name,
                    "input": {"value": in_val, "type": type(in_val).__name__ if in_val is not None else "unknown"},
                    "output": {"value": out_val, "type": type(out_val).__name__ if out_val is not None else "unknown"},
                    "confidence": 1.0,
                    "evidence": {
                        "type": "direct_observation",
                        "event_id": evt.event_id,
                        "explanation": f"Data {etype} via {fn_name}",
                    },
                })

            # C. Function Call / Return mang tính chất biến đổi (btoa, atob, JSON, custom transform)
            elif etype in ("function_call", "function_return"):
                fn_name = payload.get("function_name") or ""
                cat, step_type = self._classify_function(fn_name)
                if cat != "unknown" and cat != "custom":
                    args = payload.get("arguments") or payload.get("args") or []
                    in_val = args[0] if (isinstance(args, list) and len(args) > 0) else payload.get("input")
                    out_val = payload.get("return_value") or payload.get("result") or payload.get("output")

                    extracted_steps.append({
                        "event_id": evt.event_id,
                        "execution_id": evt.execution_id,
                        "timestamp_ns": evt.timestamp_ns,
                        "category": cat,
                        "type": step_type,
                        "function_name": fn_name,
                        "arguments": args if include_arguments else None,
                        "input": {"value": in_val, "type": type(in_val).__name__ if in_val is not None else "unknown"},
                        "output": {"value": out_val, "type": type(out_val).__name__ if out_val is not None else "unknown"},
                        "confidence": 0.95,
                        "evidence": {
                            "type": "js_hook_observation",
                            "event_id": evt.event_id,
                            "explanation": f"Observed function execution of {fn_name}",
                        },
                    })

        # 3. Quét đồ thị Property Graph để bổ sung các quan hệ TRANSFORMS / DERIVED_FROM nếu có
        try:
            graph_nodes = await self.graph_repo.get_nodes(session_id)
            graph_edges = await self.graph_repo.get_edges(session_id)
            node_map = {n.id: n for n in graph_nodes}

            for edge in graph_edges:
                rel = edge.relation_type.value if hasattr(edge.relation_type, "value") else str(edge.relation_type)
                if rel in (RelationType.TRANSFORMS.value, RelationType.DERIVED_FROM.value):
                    s_node = node_map.get(edge.source_id)
                    t_node = node_map.get(edge.target_id)
                    if s_node and t_node:
                        # Kiểm tra xem đã có trong extracted_steps chưa để tránh duplicate
                        already_present = any(
                            s.get("function_name") == (s_node.label or s_node.id)
                            for s in extracted_steps
                        )
                        if not already_present:
                            cat, step_type = self._classify_function(s_node.label or "")
                            extracted_steps.append({
                                "event_id": None,
                                "execution_id": s_node.properties.get("execution_id"),
                                "timestamp_ns": edge.created_at_ns,
                                "category": cat,
                                "type": step_type,
                                "function_name": s_node.label or s_node.id,
                                "input": {"value": s_node.properties.get("input") or s_node.label, "type": "graph_node"},
                                "output": {"value": t_node.properties.get("output") or t_node.label, "type": "graph_node"},
                                "confidence": edge.confidence,
                                "evidence": {
                                    "type": "graph_edge_inference",
                                    "edge_id": edge.id,
                                    "explanation": f"Graph relation {rel} between {s_node.label} and {t_node.label}",
                                },
                            })
        except Exception:
            pass

        # 4. Sắp xếp các bước theo trình tự thời gian
        extracted_steps.sort(key=lambda s: s.get("timestamp_ns") or 0)

        # 5. Lọc theo transformation_types nếu có
        if types_filter:
            extracted_steps = [
                s for s in extracted_steps
                if s["category"].lower() in types_filter
                or any(t in s["type"].lower() for t in types_filter)
                or any(t in s["function_name"].lower() for t in types_filter)
            ]

        # 6. Lọc theo source nếu được cung cấp
        if source_val:
            s_val_lower = str(source_val).lower()
            matched_indices: list[int] = []
            for idx, s in enumerate(extracted_steps):
                in_s = str(s.get("input", {}).get("value") or "").lower()
                out_s = str(s.get("output", {}).get("value") or "").lower()
                fn_s = str(s.get("function_name") or "").lower()
                if s_val_lower in in_s or s_val_lower in out_s or s_val_lower in fn_s:
                    matched_indices.append(idx)

            if matched_indices:
                first_idx = matched_indices[0]
                extracted_steps = extracted_steps[first_idx:]

        # 7. Lọc theo target nếu được cung cấp (Destination Sink matching)
        target_sink: dict[str, Any] | None = None
        if target_val:
            t_val_lower = str(target_val).lower()
            # Tìm trong requests xem có request / header / body nào khớp với target_val
            for req in req_rows:
                headers = safe_loads(req.headers_json) if req.headers_json else {}
                body = safe_loads(req.body_json) if req.body_json else None
                req_match = False
                matched_field = None

                if t_val_lower in str(req.id).lower() or t_val_lower in str(req.url).lower():
                    req_match = True
                    matched_field = "url"

                for hk, hv in headers.items():
                    if t_val_lower in hk.lower() or t_val_lower in str(hv).lower():
                        req_match = True
                        matched_field = f"headers.{hk}"
                        break

                if not req_match and body:
                    body_str = json.dumps(body) if isinstance(body, (dict, list)) else str(body)
                    if t_val_lower in body_str.lower():
                        req_match = True
                        matched_field = "body"

                if req_match:
                    target_sink = {
                        "type": "http_request",
                        "request_id": req.id,
                        "method": req.method,
                        "url": req.url,
                        "field": matched_field or "request",
                    }
                    break

        # Nếu không có target_val chỉ định nhưng có request sau bước cuối cùng
        if not target_sink and req_rows and extracted_steps:
            last_step_time = extracted_steps[-1].get("timestamp_ns") or 0
            later_reqs = [r for r in req_rows if r.started_at_ns >= last_step_time]
            chosen_req = later_reqs[0] if later_reqs else req_rows[-1]
            last_out = str(extracted_steps[-1].get("output", {}).get("value") or "")

            # Kiểm tra xem output của bước cuối có xuất hiện trong headers hoặc body của request không
            headers = safe_loads(chosen_req.headers_json) if chosen_req.headers_json else {}
            matched_header = None
            if last_out and len(last_out) > 3:
                for hk, hv in headers.items():
                    if last_out in str(hv) or str(hv) in last_out:
                        matched_header = hk
                        break

            target_sink = {
                "type": "http_request",
                "request_id": chosen_req.id,
                "method": chosen_req.method,
                "url": chosen_req.url,
                "field": f"headers.{matched_header}" if matched_header else "request_payload",
            }

        # 8. Giới hạn độ sâu max_depth
        if max_depth and len(extracted_steps) > max_depth:
            extracted_steps = extracted_steps[:max_depth]

        # 9. Đóng gói danh sách transformations chuẩn
        transformations: list[dict[str, Any]] = []
        pipeline_elements: list[str] = []

        # Phần tử đầu tiên trong pipeline (Nguồn dữ liệu ban đầu)
        origin_label = str(source_val) if source_val else "raw_input"
        if extracted_steps:
            first_in = extracted_steps[0].get("input", {}).get("value")
            if first_in and not source_val:
                origin_label = str(first_in) if len(str(first_in)) <= 25 else f"{str(first_in)[:22]}..."
        pipeline_elements.append(origin_label)

        for i, step in enumerate(extracted_steps, start=1):
            t_id = f"trans_{i:02d}"
            step_record = {
                "transformation_id": t_id,
                "step_number": i,
                "type": step["type"],
                "category": step["category"],
                "function_name": step["function_name"],
                "execution_id": step.get("execution_id"),
                "input": step["input"],
                "output": step["output"],
                "confidence": step["confidence"],
                "evidence": step["evidence"],
            }
            if include_arguments and "arguments" in step and step["arguments"] is not None:
                step_record["arguments"] = step["arguments"]

            transformations.append(step_record)
            pipeline_elements.append(step["function_name"])

        # Thêm sink đích vào pipeline nếu có
        if target_sink:
            field_name = target_sink.get("field") or "Header/Body"
            pipeline_elements.append(f"Destination({target_sink.get('method', 'POST')} {field_name})")

        chain_summary = " -> ".join(pipeline_elements)

        if direction == "backward":
            # Nếu yêu cầu hướng backward, đảo ngược danh sách các bước
            transformations = list(reversed(transformations))

        return {
            "session_id": session_id,
            "source": source or origin_label,
            "target": target or (target_sink if target_sink else "destination_sink"),
            "direction": direction,
            "chain_summary": chain_summary,
            "pipeline": pipeline_elements,
            "count": len(transformations),
            "transformations": transformations,
        }
