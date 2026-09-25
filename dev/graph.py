"""
Bộ Dựng Đồ thị Nhân quả Lấy Request làm Trung tâm (Request-Centric CausalGraphBuilder).
Hiện thực hóa việc bóc tách từng Field/Value của Request, kết nối với V8 Call Stack và truy vết nguồn gốc (Backward Trace) cũng như tác động của Response (Forward Trace).
"""

from __future__ import annotations
import json
import time
import uuid
from typing import Any
from dev.schema import (
    CausalEdge,
    CausalGraph,
    FunctionNode,
    NodeType,
    RelationType,
    RequestNode,
    ResponseNode,
    StateKind,
    StateNode,
    ValueNode,
    ValueRef,
)
from dev.storage import ValueStore


class CausalGraphBuilder:
    """Builder chuyên dụng cho Reverse Engineering API Data-Flow."""

    def __init__(self, session_id: str | None = None, value_store: ValueStore | None = None):
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        self.value_store = value_store or ValueStore()
        self.graph = CausalGraph(session_id=self.session_id, created_at=time.time())
        self._counters: dict[str, int] = {}

    def _next_id(self, prefix: str) -> str:
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}_{count:04d}"

    # -------------------------------------------------------------------------
    # 1. FACTORY METHODS: CÁC LOẠI NODE
    # -------------------------------------------------------------------------

    def add_state(
        self,
        kind: StateKind,
        key: str,
        value_raw: Any = None,
        url: str | None = None,
        timestamp: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StateNode:
        """Thêm State/Source ban đầu (DOM, Storage, Cookie, Location)."""
        node_id = self._next_id(f"state_{kind.value.lower()}")
        val_ref = self.value_store.store(value_raw) if value_raw is not None else None
        node = StateNode(
            id=node_id,
            node_type=NodeType.STATE,
            timestamp=timestamp or time.time(),
            kind=kind,
            key=key,
            value=val_ref,
            url=url,
            metadata=metadata or {},
        )
        self.graph.add_node(node)
        return node

    def add_dom_state(
        self,
        key: str,  # input name hoặc selector
        value: str,
        tag: str = "input",
        input_type: str = "text",
        url: str | None = None,
        timestamp: float | None = None,
    ) -> StateNode:
        """Helper thêm trạng thái DOM (input field, hidden CSRF, script SSR data)."""
        return self.add_state(
            kind=StateKind.DOM,
            key=key,
            value_raw=value,
            url=url,
            timestamp=timestamp,
            metadata={"tag": tag, "input_type": input_type},
        )

    def add_cookie_state(
        self,
        name: str,
        value: str,
        domain: str | None = None,
        url: str | None = None,
        timestamp: float | None = None,
    ) -> StateNode:
        """Helper thêm Cookie vào State."""
        return self.add_state(
            kind=StateKind.COOKIE,
            key=name,
            value_raw=value,
            url=url,
            timestamp=timestamp,
            metadata={"domain": domain},
        )

    def add_storage_state(
        self,
        key: str,
        value: Any,
        kind: str = "localStorage",
        url: str | None = None,
        timestamp: float | None = None,
    ) -> StateNode:
        """Helper thêm LocalStorage / SessionStorage vào State."""
        return self.add_state(
            kind=StateKind.STORAGE,
            key=key,
            value_raw=value,
            url=url,
            timestamp=timestamp,
            metadata={"storage_type": kind},
        )

    def add_function(
        self,
        name: str,
        file_url: str = "",
        line: int = 0,
        col: int = 0,
        is_async: bool = False,
        timestamp: float | None = None,
    ) -> FunctionNode:
        """Thêm hàm JavaScript tham gia trong chuỗi thực thi."""
        node_id = self._next_id("fn")
        node = FunctionNode(
            id=node_id,
            node_type=NodeType.FUNCTION,
            timestamp=timestamp or time.time(),
            name=name,
            file_url=file_url,
            line=line,
            col=col,
            is_async=is_async,
        )
        self.graph.add_node(node)
        return node

    def add_value(
        self,
        name: str,
        raw_val: Any,
        location_in_target: str = "body",
        parent_value_id: str | None = None,
        timestamp: float | None = None,
    ) -> ValueNode:
        """Thêm một mảnh dữ liệu cụ thể (Field / Token)."""
        node_id = self._next_id("val")
        val_ref = self.value_store.store(raw_val)
        node = ValueNode(
            id=node_id,
            node_type=NodeType.VALUE,
            timestamp=timestamp or time.time(),
            name=name,
            location_in_target=location_in_target,
            value=val_ref,
            parent_value_id=parent_value_id,
        )
        self.graph.add_node(node)
        return node

    def add_request(
        self,
        request_id: str,
        url: str,
        method: str,
        headers: dict[str, str] | None = None,
        body_raw: Any = None,
        initiator_type: str = "other",
        initiator_stack: list[str] | None = None,
        timestamp: float | None = None,
    ) -> RequestNode:
        """Thêm HTTP Request (Root của mỗi trace)."""
        node_id = self._next_id("req")
        val_ref = self.value_store.store(body_raw) if body_raw is not None else None
        node = RequestNode(
            id=node_id,
            node_type=NodeType.REQUEST,
            timestamp=timestamp or time.time(),
            request_id=request_id,
            url=url,
            method=method.upper(),
            headers=headers or {},
            body=val_ref,
            initiator_type=initiator_type,
            initiator_stack=initiator_stack or [],
        )
        self.graph.add_node(node)
        return node

    def add_response(
        self,
        request_node: RequestNode,
        status: int,
        mime_type: str,
        headers: dict[str, str] | None = None,
        body_raw: Any = None,
        timestamp: float | None = None,
    ) -> ResponseNode:
        """Thêm HTTP Response và tự động thiết lập liên kết RESPONDS_TO với Request."""
        node_id = self._next_id("res")
        val_ref = self.value_store.store(body_raw) if body_raw is not None else None
        res_node = ResponseNode(
            id=node_id,
            node_type=NodeType.RESPONSE,
            timestamp=timestamp or time.time(),
            request_id=request_node.request_id,
            status=status,
            mime_type=mime_type,
            headers=headers or {},
            body=val_ref,
        )
        self.graph.add_node(res_node)

        # Cạnh chắc chắn nhất trong graph: Request -> Response
        self.graph.add_edge(
            from_id=request_node.id,
            to_id=res_node.id,
            relation=RelationType.RESPONDS_TO,
            confidence=1.0,
            evidence=["cdp_network_pair"],
            metadata={"status": status},
        )
        return res_node

    # -------------------------------------------------------------------------
    # 2. DATA-FLOW TRACING & CORRELATION
    # -------------------------------------------------------------------------

    def build_request_lineage(
        self,
        request_node: RequestNode,
        post_data: Any = None,
    ) -> list[ValueNode]:
        """
        Phân rã Request Payload và Headers thành các ValueNode con,
        sau đó tự động truy tìm nguồn gốc từng field (Backward Correlation).
        """
        created_values: list[ValueNode] = []
        req_time = request_node.timestamp

        # 1. Phân tích Cookies trong Headers
        cookie_header = request_node.headers.get("cookie") or request_node.headers.get("Cookie") or ""
        if cookie_header:
            for ck_item in cookie_header.split(";"):
                if "=" in ck_item:
                    ck_name, ck_val = ck_item.strip().split("=", 1)
                    val_node = self.add_value(
                        name=f"Cookie:{ck_name}",
                        raw_val=ck_val,
                        location_in_target="header",
                        timestamp=req_time,
                    )
                    created_values.append(val_node)
                    # Nối Value vào Request
                    self.graph.add_edge(
                        from_id=val_node.id,
                        to_id=request_node.id,
                        relation=RelationType.SENDS,
                        confidence=1.0,
                        evidence=["cookie_header_serialization"],
                    )
                    # Tìm State tương ứng
                    self._correlate_value_to_states(val_node, ck_val, StateKind.COOKIE, ck_name)

        # 2. Phân rã Payload (JSON hoặc urlencoded form)
        fields = self._parse_payload_fields(post_data)
        for field_name, field_val in fields.items():
            val_node = self.add_value(
                name=field_name,
                raw_val=field_val,
                location_in_target="body",
                timestamp=req_time,
            )
            created_values.append(val_node)

            # Nối Value vào Request (Value BUILDS Request)
            self.graph.add_edge(
                from_id=val_node.id,
                to_id=request_node.id,
                relation=RelationType.BUILDS,
                confidence=1.0,
                evidence=["payload_field_membership"],
                metadata={"field": field_name},
            )

            # Truy ngược xem Value này sinh ra từ State nào
            self._correlate_value_to_states(val_node, field_val)

        # 3. Gắn V8 Initiator Call Stack nếu có
        if request_node.initiator_stack:
            prev_fn_id = None
            for idx, frame_str in enumerate(reversed(request_node.initiator_stack)):
                fn_name = frame_str.split("@")[0] if "@" in frame_str else frame_str
                fn_node = self.add_function(name=fn_name, file_url=frame_str, timestamp=req_time)
                if prev_fn_id:
                    self.graph.add_edge(
                        from_id=prev_fn_id,
                        to_id=fn_node.id,
                        relation=RelationType.PASSES,
                        confidence=0.95,
                        evidence=["v8_initiator_stack_call"],
                    )
                prev_fn_id = fn_node.id

            # Hàm cuối cùng trong stack là hàm gọi fetch / XHR -> BUILDS Request
            if prev_fn_id:
                self.graph.add_edge(
                    from_id=prev_fn_id,
                    to_id=request_node.id,
                    relation=RelationType.BUILDS,
                    confidence=0.98,
                    evidence=["v8_top_initiator_call"],
                )

        return created_values

    def _parse_payload_fields(self, post_data: Any) -> dict[str, Any]:
        """Trích xuất các field từ payload JSON hoặc Form Data."""
        if not post_data:
            return {}
        if isinstance(post_data, dict):
            return post_data
        if isinstance(post_data, str):
            stripped = post_data.strip()
            if stripped.startswith(("{", "[")):
                try:
                    loaded = json.loads(stripped)
                    if isinstance(loaded, dict):
                        return loaded
                except Exception:
                    pass
            # Thử parse form urlencoded: a=1&b=2
            if "=" in stripped:
                res = {}
                for part in stripped.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        res[k] = v
                return res
        return {"raw_payload": post_data}

    def _correlate_value_to_states(
        self,
        val_node: ValueNode,
        val_raw: Any,
        expected_kind: StateKind | None = None,
        key_hint: str | None = None,
    ) -> None:
        """So khớp giá trị với các StateNode hiện có để thiết lập cạnh READS."""
        val_str = str(val_raw).strip()
        if len(val_str) < 3:
            return

        for node_id, node in self.graph.nodes.items():
            if node.node_type != NodeType.STATE or not isinstance(node, StateNode):
                continue
            if expected_kind and node.kind != expected_kind:
                continue

            # A. Khớp theo Key/Name (ví dụ Cookie name hoặc DOM selector)
            key_matched = key_hint and (key_hint == node.key or key_hint in node.key)

            # B. Khớp theo Value Hash / Exact Content
            val_matched = False
            if node.value:
                state_val = self.value_store.load(node.value.ref)
                if state_val and (str(state_val) == val_str or (len(val_str) >= 6 and val_str in str(state_val))):
                    val_matched = True

            if key_matched or val_matched:
                conf = 0.99 if (key_matched and val_matched) else (0.95 if val_matched else 0.85)
                evidence = ["exact_value_match"] if val_matched else []
                if key_matched:
                    evidence.append("key_name_match")

                # Cạnh: State -> Value (State cung cấp giá trị cho Value)
                self.graph.add_edge(
                    from_id=node.id,
                    to_id=val_node.id,
                    relation=RelationType.READS,
                    confidence=conf,
                    evidence=evidence,
                    metadata={"state_kind": node.kind.value, "state_key": node.key},
                )

    def correlate_response_consumption(
        self,
        response_node: ResponseNode,
        consumer_fn_name: str,
        target_state_node: StateNode,
        extracted_token_key: str,
    ) -> None:
        """
        Thiết lập chuỗi Forward Trace khi Response được tiêu thụ:
        Response -> Function -> Value (Token) -> State (LocalStorage / Cookie)
        """
        t = response_node.timestamp + 0.05
        # 1. Hàm bóc tách response
        fn_node = self.add_function(name=consumer_fn_name, timestamp=t)
        self.graph.add_edge(
            from_id=response_node.id,
            to_id=fn_node.id,
            relation=RelationType.CONSUMES,
            confidence=0.98,
            evidence=["response_handler_callback"],
        )

        # 2. Giá trị được trích xuất
        if target_state_node.value:
            tok_val = self.value_store.load(target_state_node.value.ref)
        else:
            tok_val = f"extracted_{extracted_token_key}"

        val_node = self.add_value(name=extracted_token_key, raw_val=tok_val, timestamp=t + 0.01)
        self.graph.add_edge(
            from_id=fn_node.id,
            to_id=val_node.id,
            relation=RelationType.PRODUCES,
            confidence=0.96,
            evidence=["token_extraction"],
        )

        # 3. Ghi vào State (Storage/Cookie)
        self.graph.add_edge(
            from_id=val_node.id,
            to_id=target_state_node.id,
            relation=RelationType.WRITES,
            confidence=0.99,
            evidence=["state_storage_write"],
            metadata={"key": target_state_node.key},
        )
