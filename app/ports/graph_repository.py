from typing import Protocol

from app.domain.graph.edges import GraphEdge
from app.domain.graph.nodes import GraphNode


class GraphRepositoryPort(Protocol):
    """Port giao tiếp quản lý lưu trữ và truy vấn Property Graph."""

    async def save_nodes(self, nodes: list[GraphNode]) -> None:
        """Lưu danh sách node vào kho đồ thị."""
        ...

    async def save_edges(self, edges: list[GraphEdge]) -> None:
        """Lưu danh sách edge cùng evidence đi kèm."""
        ...

    async def get_node(self, node_id: str) -> GraphNode | None:
        """Lấy thông tin chi tiết của một Node theo ID."""
        ...

    async def get_nodes(
        self,
        session_id: str,
        node_type: str | None = None,
    ) -> list[GraphNode]:
        """Lấy danh sách các node của một session, hỗ trợ lọc theo loại node."""
        ...

    async def get_edges(
        self,
        session_id: str,
        relation_type: str | None = None,
    ) -> list[GraphEdge]:
        """Lấy danh sách các edge của một session, hỗ trợ lọc theo relation."""
        ...

    async def get_incoming_edges(self, target_node_id: str) -> list[GraphEdge]:
        """Lấy các cạnh trỏ tới node mục tiêu (phục vụ backward traversal)."""
        ...

    async def get_outgoing_edges(self, source_node_id: str) -> list[GraphEdge]:
        """Lấy các cạnh xuất phát từ node nguồn (phục vụ forward traversal)."""
        ...

    async def delete_session_graph(self, session_id: str) -> None:
        """Xóa toàn bộ nodes, edges và evidence của một session."""
        ...

    async def delete_nodes(self, node_ids: list[str]) -> None:
        """Xóa danh sách nodes theo ID và các edges kết nối tới chúng."""
        ...

    async def delete_edges(self, edge_ids: list[str]) -> None:
        """Xóa danh sách edges theo ID."""
        ...
