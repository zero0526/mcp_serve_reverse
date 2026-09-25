"""
Schema Đồ thị Nhân quả Lấy Request làm Trung tâm (Request-Centric & Value-Flow Causal Graph).
Được thiết kế chuyên biệt cho Reverse Engineering:
1. Root của mỗi trace là HTTP Request (RequestNode).
2. Backward Trace: Từng field của Request được sinh ra từ đâu (ValueNode <- FunctionNode <- StateNode/DOM/Cookie/Storage).
3. Forward Trace: Response được xử lý ra sao và tác động tới những đâu (ResponseNode -> ValueNode -> FunctionNode -> StateNode -> Next Request).
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Các nhóm Node chuyên biệt trong đồ thị phân tích Reverse."""
    REQUEST = "REQUEST"      # HTTP Request (Root của mỗi trace)
    RESPONSE = "RESPONSE"    # HTTP Response (tương ứng với Request)
    FUNCTION = "FUNCTION"    # Hàm JS tham gia tạo request hoặc tiêu thụ response
    VALUE = "VALUE"          # Mảnh giá trị cụ thể (field, token, query param, payload chunk)
    STATE = "STATE"          # Trạng thái môi trường (DOM input, LocalStorage, Cookie, Location)


class StateKind(str, Enum):
    """Phân loại trạng thái/nguồn ban đầu."""
    DOM = "DOM"                # Thẻ input, script tag, hidden token, element text
    STORAGE = "STORAGE"        # LocalStorage, SessionStorage
    COOKIE = "COOKIE"          # Browser Cookie Jar
    LOCATION = "LOCATION"      # URL, pathname, hash, query params


class RelationType(str, Enum):
    """Quan hệ nhân quả giữa các Node."""
    # --- Backward (Truy ngược nguyên nhân tạo Request) ---
    READS = "READS"            # Function đọc giá trị từ State (DOM/Storage/Cookie)
    PASSES = "PASSES"          # Value được truyền làm tham số vào Function
    PRODUCES = "PRODUCES"      # Function tính toán sinh ra Value mới (hash, encode, build)
    BUILDS = "BUILDS"          # Value được đưa vào cấu thành Body hoặc Header của Request
    SENDS = "SENDS"            # Trình duyệt gửi Request đi qua Network

    # --- Cặp đôi mạng ---
    RESPONDS_TO = "RESPONDS_TO"  # Response là kết quả trả về của Request

    # --- Forward (Truy xuôi tác động của Response) ---
    CONSUMES = "CONSUMES"      # Function bóc tách và tiêu thụ Response hoặc Value
    WRITES = "WRITES"          # Function ghi Value vào State (Storage/Cookie/DOM)
    TRIGGERS = "TRIGGERS"      # State hoặc Function kích hoạt Request tiếp theo


class ValueRef(BaseModel):
    """Tham chiếu dữ liệu tách rời để bảo vệ đồ thị không bị phình to bởi payload lớn."""
    type: str = Field(description="Kiểu dữ liệu: string, json, blob, number, boolean")
    hash: str = Field(description="Mã hash SHA-256 nội dung: sha256:...")
    size: int = Field(description="Kích thước dữ liệu tính theo bytes")
    ref: str = Field(description="ID/URI truy xuất nội dung gốc trong ValueStore")
    preview: str | None = Field(default=None, description="Trích đoạn ngắn để kiểm tra nhanh")


class BaseNode(BaseModel):
    """Lớp cơ sở cho mọi Node trong Causal Graph."""
    id: str = Field(description="Định danh node: req_xxx, res_xxx, val_xxx, fn_xxx, state_xxx")
    node_type: NodeType = Field(description="Loại node")
    timestamp: float = Field(description="Thời điểm diễn ra (POSIX timestamp)")


class RequestNode(BaseNode):
    """Node Trung tâm (Root của mỗi Trace). Đại diện cho một HTTP Request."""
    node_type: Literal[NodeType.REQUEST] = NodeType.REQUEST
    request_id: str = Field(description="CDP Network requestId")
    url: str = Field(description="Full URL của request")
    method: str = Field(description="GET, POST, PUT, DELETE...")
    headers: dict[str, str] = Field(default_factory=dict, description="Request headers")
    query_params: dict[str, str] = Field(default_factory=dict, description="Parsed query params")
    body: ValueRef | None = Field(default=None, description="Tham chiếu tới Request Body")
    initiator_type: str = Field(default="other", description="script, parser, other...")
    initiator_stack: list[str] = Field(default_factory=list, description="V8 Call Stack (hàm JS kích hoạt)")
    frame_id: str | None = None
    execution_context_id: int | None = None


class ResponseNode(BaseNode):
    """Đại diện cho HTTP Response tương ứng với một Request."""
    node_type: Literal[NodeType.RESPONSE] = NodeType.RESPONSE
    request_id: str = Field(description="Liên kết tới Request tương ứng")
    status: int = Field(description="HTTP status code: 200, 302, 401...")
    mime_type: str = Field(description="MIME type: application/json, text/html...")
    headers: dict[str, str] = Field(default_factory=dict, description="Response headers")
    body: ValueRef | None = Field(default=None, description="Tham chiếu tới Response Body")


class ValueNode(BaseNode):
    """Mảnh giá trị cụ thể cấu thành nên Request hoặc được bóc tách từ Response."""
    node_type: Literal[NodeType.VALUE] = NodeType.VALUE
    name: str = Field(description="Tên trường dữ liệu: email, password, csrf_token, Authorization...")
    location_in_target: str = Field(
        default="body",
        description="Vị trí trong Request/Response: body, header, query, cookie"
    )
    value: ValueRef = Field(description="Tham chiếu giá trị")
    parent_value_id: str | None = Field(default=None, description="ID của Value cha nếu là field con của JSON object")


class FunctionNode(BaseNode):
    """Hàm JavaScript tham gia vào chuỗi tính toán/xử lý."""
    node_type: Literal[NodeType.FUNCTION] = NodeType.FUNCTION
    name: str = Field(description="Tên hàm: login, buildPayload, encrypt, handleResponse")
    file_url: str = Field(default="", description="File JS chứa hàm")
    line: int = Field(default=0)
    col: int = Field(default=0)
    is_async: bool = Field(default=False)


class StateNode(BaseNode):
    """Trạng thái môi trường cung cấp giá trị ban đầu hoặc nhận cập nhật từ Response."""
    node_type: Literal[NodeType.STATE] = NodeType.STATE
    kind: StateKind = Field(description="DOM, STORAGE, COOKIE, LOCATION")
    key: str = Field(description="Định danh: Selector '#email', Storage key 'token', Cookie name 'SESSION_ID'")
    value: ValueRef | None = Field(default=None, description="Giá trị hiện tại của state")
    url: str | None = Field(default=None, description="URL trang chứa state")
    metadata: dict[str, Any] = Field(default_factory=dict)


# Union type cho tất cả Node
GraphNode = RequestNode | ResponseNode | ValueNode | FunctionNode | StateNode


class CausalEdge(BaseModel):
    """Cạnh quan hệ nhân quả kết nối các Node."""
    id: str
    from_node: str
    to_node: str
    relation: RelationType
    confidence: float = Field(ge=0.0, le=1.0)
    tier: Literal["DIRECT", "STRONG", "WEAK"] = "DIRECT"
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CausalGraph(BaseModel):
    """Đồ thị Causal Graph hoàn chỉnh theo mô hình Request-Centric."""
    session_id: str
    created_at: float
    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: list[CausalEdge] = Field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: RelationType,
        confidence: float,
        evidence: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> CausalEdge:
        tier: Literal["DIRECT", "STRONG", "WEAK"] = (
            "DIRECT" if confidence >= 0.99 else ("STRONG" if confidence >= 0.8 else "WEAK")
        )
        edge = CausalEdge(
            id=f"edge_{len(self.edges) + 1:04d}",
            from_node=from_id,
            to_node=to_id,
            relation=relation,
            confidence=confidence,
            tier=tier,
            evidence=evidence,
            metadata=metadata or {},
        )
        self.edges.append(edge)
        return edge

    # -------------------------------------------------------------------------
    # TRUY VẤN CỐT LÕI CHO REVERSE ENGINEERING
    # -------------------------------------------------------------------------

    def trace_backward(self, request_id: str) -> dict[str, Any]:
        """
        Truy ngược nguồn gốc của từng trường trong Request:
        Request #N
          ├── Field X ◄── Function ◄── State (DOM / Storage / Cookie)
          └── Header Y ◄── State
        """
        req_node = self.nodes.get(request_id)
        if not req_node or req_node.node_type != NodeType.REQUEST:
            return {"error": f"Node {request_id} không phải là RequestNode"}

        # 1. Tách biệt các ValueNode cấu thành payload/header và FunctionNode trong V8 stack
        field_lineages = []
        initiator_calls = []
        for edge in self.edges:
            if edge.to_node == request_id and edge.relation in [RelationType.BUILDS, RelationType.SENDS]:
                from_n = self.nodes.get(edge.from_node)
                if not from_n:
                    continue

                lineage_item = {
                    "edge": edge,
                    "node": from_n,
                    "origins": self._trace_upstream_recursive(from_n.id, depth=0, max_depth=5),
                }
                if from_n.node_type == NodeType.VALUE:
                    field_lineages.append(lineage_item)
                elif from_n.node_type == NodeType.FUNCTION:
                    initiator_calls.append(lineage_item)

        return {
            "root_request": req_node,
            "field_origins": field_lineages,
            "initiator_calls": initiator_calls,
        }

    def trace_forward(self, response_id: str) -> dict[str, Any]:
        """
        Truy xuôi tác động của Response:
        Response #N
          └── Value (Token) ──> Function ──> State (LocalStorage) ──> Request #N+1
        """
        res_node = self.nodes.get(response_id)
        if not res_node or res_node.node_type != NodeType.RESPONSE:
            return {"error": f"Node {response_id} không phải là ResponseNode"}

        impacts = []
        for edge in self.edges:
            if edge.from_node == response_id and edge.relation == RelationType.CONSUMES:
                to_n = self.nodes.get(edge.to_node)
                if not to_n:
                    continue

                impact_item = {
                    "edge": edge,
                    "node": to_n,
                    "downstream": self._trace_downstream_recursive(to_n.id, depth=0, max_depth=5),
                }
                impacts.append(impact_item)

        return {
            "root_response": res_node,
            "impacts": impacts,
        }

    def _trace_upstream_recursive(self, node_id: str, depth: int, max_depth: int) -> list[dict[str, Any]]:
        if depth >= max_depth:
            return []
        upstream = []
        for edge in self.edges:
            if edge.to_node == node_id and edge.from_node in self.nodes:
                parent_node = self.nodes[edge.from_node]
                upstream.append({
                    "edge": edge,
                    "node": parent_node,
                    "ancestors": self._trace_upstream_recursive(parent_node.id, depth + 1, max_depth),
                })
        return upstream

    def _trace_downstream_recursive(self, node_id: str, depth: int, max_depth: int) -> list[dict[str, Any]]:
        if depth >= max_depth:
            return []
        downstream = []
        for edge in self.edges:
            if edge.from_node == node_id and edge.to_node in self.nodes:
                child_node = self.nodes[edge.to_node]
                downstream.append({
                    "edge": edge,
                    "node": child_node,
                    "descendants": self._trace_downstream_recursive(child_node.id, depth + 1, max_depth),
                })
        return downstream
