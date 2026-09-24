import json
import hashlib
from typing import Any

from app.adapters.graph.stack_parser import StackFrame, parse_v8_stack
from app.domain.graph.edges import EdgeEvidence, GraphEdge
from app.domain.graph.nodes import GraphNode, NodeType
from app.domain.graph.relations import RelationType
from app.infrastructure.serialization.json import parse_smart_payload, safe_dumps, safe_loads


def _hash_val(val: Any) -> str:
    s = str(val) if val is not None else ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _flatten_leaves(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Đệ quy phân rã dictionary/list thành danh sách các cặp (path, leaf_value)."""
    data = parse_smart_payload(data)

    leaves: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            sub_path = f"{prefix}.{k}" if prefix else str(k)
            leaves.extend(_flatten_leaves(v, sub_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            sub_path = f"{prefix}[{i}]"
            leaves.extend(_flatten_leaves(item, sub_path))
    else:
        if data is not None:
            leaves.append((prefix, data))
    return leaves


class GraphProjector:
    """Projector thuần logic chuyển đổi Event Store thành Graph Nodes & Edges có bằng chứng."""

    def project(
        self,
        session_id: str,
        requests: list[dict[str, Any]],
        responses: list[dict[str, Any]],
        storage_ops: list[dict[str, Any]],
        trace_events: list[dict[str, Any]] | None = None,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        events = trace_events or []

        # 1. SESSION NODE
        sess_node_id = f"node_sess_{session_id}"
        nodes.append(
            GraphNode(
                id=sess_node_id,
                session_id=session_id,
                node_type=NodeType.SESSION,
                label=f"Session {session_id}",
                entity_id=session_id,
                properties={"session_id": session_id},
            )
        )

        # 2. STORAGE NODES (Group by storage_type:storage_key)
        storage_node_map: dict[str, GraphNode] = {}
        for sop in storage_ops:
            stype = sop.get("storage_type", "local_storage")
            skey = sop.get("storage_key", "*all*")
            node_key = f"{stype}:{skey}"
            if node_key not in storage_node_map:
                snode_id = f"node_stor_{session_id}_{stype}_{_hash_val(skey)}"
                snode = GraphNode(
                    id=snode_id,
                    session_id=session_id,
                    node_type=NodeType.STORAGE_ENTRY,
                    label=f"{stype}.{skey}",
                    entity_id=node_key,
                    properties={
                        "storage_type": stype,
                        "storage_key": skey,
                        "last_value_ref": sop.get("value_ref"),
                    },
                )
                storage_node_map[node_key] = snode
                nodes.append(snode)

                # Cạnh Session -> Storage Node
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        source_id=sess_node_id,
                        target_id=snode_id,
                        relation_type=RelationType.CONTAINS,
                        confidence=1.0,
                        provenance_status="observed",
                        properties={"scope": "session"},
                    )
                )

        # 3. REQUEST NODES
        req_node_map: dict[str, GraphNode] = {}
        for req in requests:
            req_id = req.get("id") or req.get("request_id") or "unknown_req"
            rnode_id = f"node_req_{session_id}_{req_id}"
            headers = safe_loads(req.get("headers_json")) if isinstance(req.get("headers_json"), str) else req.get("headers", {})
            query = safe_loads(req.get("query_json")) if isinstance(req.get("query_json"), str) else req.get("query", {})
            raw_body = safe_loads(req.get("body_json")) if isinstance(req.get("body_json"), str) else req.get("body")
            body = parse_smart_payload(raw_body)

            rnode = GraphNode(
                id=rnode_id,
                session_id=session_id,
                node_type=NodeType.HTTP_REQUEST,
                label=f"{req.get('method', 'GET')} {req.get('path') or req.get('url', '')}",
                entity_id=req_id,
                properties={
                    "request_id": req_id,
                    "method": req.get("method", "GET"),
                    "url": req.get("url", ""),
                    "path": req.get("path", ""),
                    "headers": headers,
                    "query": query,
                    "body": body,
                    "started_at_ns": req.get("started_at_ns"),
                },
            )
            req_node_map[req_id] = rnode
            nodes.append(rnode)

            # Session CONTAINS Request
            edges.append(
                GraphEdge(
                    session_id=session_id,
                    source_id=sess_node_id,
                    target_id=rnode_id,
                    relation_type=RelationType.CONTAINS,
                    confidence=1.0,
                    provenance_status="observed",
                )
            )

        # 4. RESPONSE NODES & ASSOCIATED_WITH REQUEST
        for res in responses:
            res_id = res.get("id") or f"res_{_hash_val(res.get('request_id', ''))}"
            req_id = res.get("request_id")
            res_node_id = f"node_res_{session_id}_{res_id}"

            res_node = GraphNode(
                id=res_node_id,
                session_id=session_id,
                node_type=NodeType.HTTP_RESPONSE,
                label=f"Response {res.get('status_code', 200)}",
                entity_id=res_id,
                properties={
                    "response_id": res_id,
                    "request_id": req_id,
                    "status_code": res.get("status_code"),
                    "headers": safe_loads(res.get("headers_json")) if isinstance(res.get("headers_json"), str) else res.get("headers", {}),
                    "body": parse_smart_payload(safe_loads(res.get("body_json")) if isinstance(res.get("body_json"), str) else res.get("body")),
                },
            )
            nodes.append(res_node)

            if req_id and req_id in req_node_map:
                edges.append(
                    GraphEdge(
                        session_id=session_id,
                        source_id=req_node_map[req_id].id,
                        target_id=res_node_id,
                        relation_type=RelationType.ASSOCIATED_WITH,
                        confidence=1.0,
                        provenance_status="observed",
                        evidence_list=[
                            EdgeEvidence(
                                evidence_type="network_correlation",
                                explanation=f"Request {req_id} matched response {res_id}",
                            )
                        ],
                    )
                )

        # 5. DATA LINEAGE INFERENCE (Storage <-> Request & Value Matching)
        # Đối chiếu xem storage reads nào xảy ra trước request và khớp giá trị/khóa
        for req in requests:
            req_id = req.get("id") or req.get("request_id")
            if not req_id or req_id not in req_node_map:
                continue

            rnode = req_node_map[req_id]
            req_time = req.get("started_at_ns") or 0
            headers = rnode.properties.get("headers", {})
            body = rnode.properties.get("body")
            headers_str = safe_dumps(headers).lower()
            body_str = safe_dumps(body).lower() if body else ""

            # Kiểm tra các thao tác storage đã xảy ra
            for sop in storage_ops:
                s_time = sop.get("timestamp_ns") or 0
                stype = sop.get("storage_type", "local_storage")
                skey = sop.get("storage_key", "")
                op = sop.get("operation", "")
                val_ref = sop.get("value_ref")
                node_key = f"{stype}:{skey}"

                if node_key not in storage_node_map:
                    continue
                snode = storage_node_map[node_key]

                # Nếu là thao tác đọc (read) diễn ra trước hoặc gần thời điểm request
                if op == "read":
                    matched = False
                    explanation = ""

                    # Khớp theo tên khóa (vd: key="auth_token" xuất hiện trong request header Authorization)
                    if skey and (skey.lower() in headers_str or skey.lower() in body_str):
                        matched = True
                        explanation = f"Storage key '{skey}' matched in request payload"

                    # Hoặc khớp theo giá trị thực tế nếu có
                    if val_ref and (str(val_ref).lower() in headers_str or str(val_ref).lower() in body_str):
                        matched = True
                        explanation = f"Value of '{skey}' observed directly in request payload"

                    # Hoặc là cờ "token" trong Authorization header
                    if "auth" in skey.lower() or "token" in skey.lower():
                        if "authorization" in headers_str:
                            matched = True
                            explanation = f"Authorization header correlates with read of '{skey}'"

                    if matched:
                        edges.append(
                            GraphEdge(
                                session_id=session_id,
                                source_id=snode.id,
                                target_id=rnode.id,
                                relation_type=RelationType.READS_FROM,
                                confidence=0.95,
                                provenance_status="inferred",
                                properties={"storage_key": skey, "operation": "read"},
                                evidence_list=[
                                    EdgeEvidence(
                                        evidence_type="value_or_key_correlation",
                                        source_event_id=sop.get("event_id"),
                                        confidence=0.95,
                                        explanation=explanation,
                                    )
                                ],
                            )
                        )

                # Nếu là thao tác ghi (write) diễn ra sau khi nhận response hoặc sau request
                elif op == "write":
                    if s_time >= req_time:
                        edges.append(
                            GraphEdge(
                                session_id=session_id,
                                source_id=rnode.id,
                                target_id=snode.id,
                                relation_type=RelationType.STORES_IN,
                                confidence=0.90,
                                provenance_status="observed",
                                properties={"storage_key": skey, "operation": "write"},
                                evidence_list=[
                                    EdgeEvidence(
                                        evidence_type="subsequent_storage_write",
                                        source_event_id=sop.get("event_id"),
                                        confidence=0.90,
                                        explanation=f"Storage '{skey}' written during or after request workflow",
                                    )
                                ],
                            )
                        )

        # 6. VALUE NODES & USED_IN EDGES
        # Trích xuất các lá dữ liệu quan trọng trong Request (tên, tham số)
        for req_id, rnode in req_node_map.items():
            body = rnode.properties.get("body")
            if body:
                leaves = _flatten_leaves(body, prefix="body")
                for path, val in leaves:
                    if isinstance(val, (str, int, float, bool)):
                        val_node_id = f"node_val_{session_id}_{req_id}_{_hash_val(path)}"
                        val_node = GraphNode(
                            id=val_node_id,
                            session_id=session_id,
                            node_type=NodeType.VALUE,
                            label=f"Val: {path}={val}",
                            entity_id=path,
                            properties={"path": path, "value": val, "raw_type": type(val).__name__},
                        )
                        nodes.append(val_node)

                        edges.append(
                            GraphEdge(
                                session_id=session_id,
                                source_id=val_node_id,
                                target_id=rnode.id,
                                relation_type=RelationType.USED_IN,
                                confidence=1.0,
                                provenance_status="observed",
                                properties={"path": path},
                            )
                        )

        # 7. PRE-REQUEST FUNCTION EXECUTION GRAPH
        func_node_map: dict[str, GraphNode] = {}

        def _get_or_create_fn_node(frame: StackFrame) -> GraphNode:
            f_key = f"{frame.function_name}@{frame.file_url}:{frame.line_no}"
            if f_key not in func_node_map:
                f_node_id = f"node_fn_{session_id}_{_hash_val(f_key)}"
                fnode = GraphNode(
                    id=f_node_id,
                    session_id=session_id,
                    node_type=NodeType.FUNCTION_EXECUTION,
                    label=f"fn: {frame.function_name}",
                    entity_id=f_key,
                    properties={
                        "function_name": frame.function_name,
                        "file_url": frame.file_url,
                        "line_no": frame.line_no,
                        "col_no": frame.col_no,
                        "raw_frame": frame.raw_frame,
                    },
                )
                func_node_map[f_key] = fnode
                nodes.append(fnode)
            return func_node_map[f_key]

        def _link_call_chain(frames: list[StackFrame]) -> GraphNode | None:
            if not frames:
                return None
            prev_fnode = None
            for frame in reversed(frames):
                fnode = _get_or_create_fn_node(frame)
                if prev_fnode and prev_fnode.id != fnode.id:
                    edge_exists = any(
                        e.source_id == prev_fnode.id
                        and e.target_id == fnode.id
                        and e.relation_type == RelationType.CALLS
                        for e in edges
                    )
                    if not edge_exists:
                        edges.append(
                            GraphEdge(
                                session_id=session_id,
                                source_id=prev_fnode.id,
                                target_id=fnode.id,
                                relation_type=RelationType.CALLS,
                                confidence=1.0,
                                provenance_status="observed",
                            )
                        )
                prev_fnode = fnode
            return prev_fnode

        for ev in events:
            ev_type = ev.get("event_type", "")
            payload = (
                safe_loads(ev.get("payload_json"))
                if isinstance(ev.get("payload_json"), str)
                else ev.get("payload", {})
            )
            metadata = (
                safe_loads(ev.get("metadata_json"))
                if isinstance(ev.get("metadata_json"), str)
                else ev.get("metadata", {})
            )
            req_id = payload.get("request_id") if isinstance(payload, dict) else None

            if ev_type == "network_request":
                rnode = req_node_map.get(req_id) if req_id else None
                if not rnode and isinstance(payload, dict):
                    req_url = payload.get("url")
                    if req_url:
                        for rn in req_node_map.values():
                            if rn.properties.get("url") == req_url:
                                rnode = rn
                                break

                stack_str = (
                    metadata.get("stack")
                    or metadata.get("stack_trace")
                    or (payload.get("stack") if isinstance(payload, dict) else None)
                    or (payload.get("caller_stack") if isinstance(payload, dict) else None)
                )
                frames = parse_v8_stack(stack_str)
                top_fnode = _link_call_chain(frames)

                if top_fnode and rnode:
                    edge_exists = any(
                        e.source_id == top_fnode.id
                        and e.target_id == rnode.id
                        and e.relation_type == RelationType.CALLS
                        for e in edges
                    )
                    if not edge_exists:
                        edges.append(
                            GraphEdge(
                                session_id=session_id,
                                source_id=top_fnode.id,
                                target_id=rnode.id,
                                relation_type=RelationType.CALLS,
                                confidence=1.0,
                                provenance_status="observed",
                                properties={"action": "dispatches_request"},
                            )
                        )

        # 8. CRYPTO & SERIALIZATION OPERATIONS GRAPH
        for ev in events:
            ev_type = ev.get("event_type", "")
            if ev_type in ["crypto_operation", "serialize"]:
                payload = (
                    safe_loads(ev.get("payload_json"))
                    if isinstance(ev.get("payload_json"), str)
                    else ev.get("payload", {})
                )
                metadata = (
                    safe_loads(ev.get("metadata_json"))
                    if isinstance(ev.get("metadata_json"), str)
                    else ev.get("metadata", {})
                )
                crypto_id = f"node_crypto_{session_id}_{ev.get('event_id', _hash_val(str(payload)))}"

                if ev_type == "crypto_operation":
                    cnode = GraphNode(
                        id=crypto_id,
                        session_id=session_id,
                        node_type=NodeType.CRYPTO_OPERATION,
                        label=f"Crypto: {payload.get('operation')} ({payload.get('algorithm')})",
                        properties=payload,
                    )
                    nodes.append(cnode)

                    stack_str = (
                        metadata.get("stack")
                        or metadata.get("stack_trace")
                        or (payload.get("caller_stack") if isinstance(payload, dict) else None)
                    )
                    frames = parse_v8_stack(stack_str)
                    top_fnode = _link_call_chain(frames)
                    if top_fnode:
                        edges.append(
                            GraphEdge(
                                session_id=session_id,
                                source_id=top_fnode.id,
                                target_id=crypto_id,
                                relation_type=RelationType.TRANSFORMS,
                                confidence=1.0,
                                provenance_status="observed",
                            )
                        )

        # 9. POST-REQUEST RESPONSE CONSUMER & TAINT TRACKING GRAPH
        for ev in events:
            ev_type = ev.get("event_type", "")
            payload = (
                safe_loads(ev.get("payload_json"))
                if isinstance(ev.get("payload_json"), str)
                else ev.get("payload", {})
            )
            metadata = (
                safe_loads(ev.get("metadata_json"))
                if isinstance(ev.get("metadata_json"), str)
                else ev.get("metadata", {})
            )

            if ev_type in ["response_consumed", "response_field_read"]:
                req_id = payload.get("request_id") if isinstance(payload, dict) else None
                stack_str = (
                    metadata.get("stack")
                    or metadata.get("stack_trace")
                    or (payload.get("caller_stack") if isinstance(payload, dict) else None)
                    or (payload.get("reader_stack") if isinstance(payload, dict) else None)
                )
                frames = parse_v8_stack(stack_str)
                top_fnode = _link_call_chain(frames)

                if top_fnode:
                    # Nối response node tới consumer node
                    res_node = next(
                        (
                            n
                            for n in nodes
                            if n.node_type == NodeType.HTTP_RESPONSE
                            and (n.properties.get("request_id") == req_id or (req_id and req_id in (n.entity_id or "")))
                        ),
                        None,
                    )
                    if not res_node:
                        res_node = next((n for n in nodes if n.node_type == NodeType.HTTP_RESPONSE), None)

                    if res_node:
                        edge_exists = any(
                            e.source_id == res_node.id
                            and e.target_id == top_fnode.id
                            and e.relation_type == RelationType.CONSUMES
                            and e.properties.get("operation") == ev_type
                            and e.properties.get("field") == (payload.get("field") if isinstance(payload, dict) else None)
                            for e in edges
                        )
                        if not edge_exists:
                            edges.append(
                                GraphEdge(
                                    session_id=session_id,
                                    source_id=res_node.id,
                                    target_id=top_fnode.id,
                                    relation_type=RelationType.CONSUMES,
                                    confidence=1.0,
                                    provenance_status="observed",
                                    properties={
                                        "operation": ev_type,
                                        "field": payload.get("field") if isinstance(payload, dict) else None,
                                    },
                                )
                            )

        return nodes, edges


graph_projector = GraphProjector()
