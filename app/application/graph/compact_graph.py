from typing import Any
from urllib.parse import urlparse

from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.domain.graph.nodes import NodeType
from app.domain.graph.relations import RelationType
from app.ports.graph_repository import GraphRepositoryPort

STATIC_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".css", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".webm", ".map"
)

TRACKING_DOMAINS = (
    "google-analytics.com",
    "googletagmanager.com",
    "sentry.io",
    "doubleclick.net",
    "facebook.net",
    "clarity.ms",
    "mixpanel.com",
)

FRAMEWORK_INTERNALS = (
    "__webpack_require__",
    "webpackJsonp",
    "webpackAsyncContext",
    "regeneratorRuntime",
    "_interopRequireDefault",
    "_interopRequireWildcard",
    "_slicedToArray",
    "_toConsumableArray",
    "_asyncToGenerator",
    "scheduleCallback",
    "performConcurrentWorkOnRoot",
    "workLoopConcurrent",
)


class CompactGraphUseCase:
    """Use case tinh gọn và cắt tỉa đồ thị (Graph Compaction & Pruning) để loại bỏ các node nhiễu."""

    def __init__(
        self,
        graph_repository: GraphRepositoryPort | None = None,
        session_factory=AsyncSessionLocal,
    ):
        self.graph_repo = graph_repository or SQLiteGraphRepository(session_factory)

    def _is_static_url(self, url: str) -> bool:
        if not url:
            return False
        parsed = urlparse(url.lower())
        path = parsed.path
        if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
            return True
        if any(domain in parsed.netloc for domain in TRACKING_DOMAINS):
            return True
        return False

    async def execute(
        self,
        session_id: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        opts = options or {}
        prune_static = opts.get("prune_static", True)
        prune_internals = opts.get("prune_internals", True)
        prune_isolated = opts.get("prune_isolated", True)
        keep_node_ids = set(opts.get("keep_node_ids") or [])

        # 1. Nạp toàn bộ nodes và edges của session
        nodes = await self.graph_repo.get_nodes(session_id)
        edges = await self.graph_repo.get_edges(session_id)

        node_map = {n.id: n for n in nodes}
        incoming_edges: dict[str, list[Any]] = {n.id: [] for n in nodes}
        outgoing_edges: dict[str, list[Any]] = {n.id: [] for n in nodes}

        for e in edges:
            if e.target_id in incoming_edges:
                incoming_edges[e.target_id].append(e)
            if e.source_id in outgoing_edges:
                outgoing_edges[e.source_id].append(e)

        to_prune_ids: set[str] = set()

        # 2. Quy tắc 1: Cắt tỉa Static Resource Requests & Responses
        if prune_static:
            pruned_req_node_ids: set[str] = set()
            for n in nodes:
                ntype = (
                    n.node_type.value
                    if hasattr(n.node_type, "value")
                    else str(n.node_type)
                )
                if ntype == NodeType.HTTP_REQUEST.value:
                    url = n.properties.get("url") or ""
                    path = n.properties.get("path") or ""
                    if self._is_static_url(url) or self._is_static_url(path):
                        pruned_req_node_ids.add(n.id)
                        to_prune_ids.add(n.id)

            # Cắt tỉa các Response liên kết với Request tĩnh
            for n in nodes:
                ntype = (
                    n.node_type.value
                    if hasattr(n.node_type, "value")
                    else str(n.node_type)
                )
                if ntype == NodeType.HTTP_RESPONSE.value:
                    # Kiểm tra xem có phải response của request tĩnh không
                    in_edges = incoming_edges.get(n.id, [])
                    if in_edges and all(e.source_id in pruned_req_node_ids for e in in_edges):
                        to_prune_ids.add(n.id)

        # 3. Quy tắc 2: Cắt tỉa Framework Internals
        if prune_internals:
            for n in nodes:
                ntype = (
                    n.node_type.value
                    if hasattr(n.node_type, "value")
                    else str(n.node_type)
                )
                if ntype == NodeType.FUNCTION_EXECUTION.value:
                    fn_name = str(n.properties.get("function_name") or n.label or "")
                    if any(internal.lower() in fn_name.lower() for internal in FRAMEWORK_INTERNALS):
                        # Kiểm tra xem hàm này có tạo ra cạnh nghiệp vụ quan trọng không
                        has_critical_edge = False
                        for out_e in outgoing_edges.get(n.id, []):
                            rel_type = (
                                out_e.relation_type.value
                                if hasattr(out_e.relation_type, "value")
                                else str(out_e.relation_type)
                            )
                            if rel_type in (
                                RelationType.TRANSFORMS.value,
                                RelationType.STORES_IN.value,
                                RelationType.READS_FROM.value,
                            ):
                                has_critical_edge = True
                                break
                            if rel_type == RelationType.CALLS.value and out_e.target_id not in to_prune_ids:
                                target_node = node_map.get(out_e.target_id)
                                if target_node:
                                    t_type = (
                                        target_node.node_type.value
                                        if hasattr(target_node.node_type, "value")
                                        else str(target_node.node_type)
                                    )
                                    if t_type == NodeType.HTTP_REQUEST.value:
                                        has_critical_edge = True
                                        break

                        if not has_critical_edge:
                            to_prune_ids.add(n.id)

        # 4. Quy tắc 3: Cắt tỉa Orphan / Isolated Nodes (ngoại trừ Session Node và HTTP Request nghiệp vụ)
        if prune_isolated:
            for n in nodes:
                ntype = (
                    n.node_type.value
                    if hasattr(n.node_type, "value")
                    else str(n.node_type)
                )
                if ntype in (NodeType.SESSION.value, NodeType.HTTP_REQUEST.value):
                    continue
                if n.id in to_prune_ids:
                    continue

                # Node chỉ có duy nhất cạnh CONTAINS từ session mà không liên kết tới ai khác
                non_contains_in = [
                    e for e in incoming_edges.get(n.id, [])
                    if (e.relation_type.value if hasattr(e.relation_type, "value") else str(e.relation_type)) != RelationType.CONTAINS.value
                ]
                non_contains_out = [
                    e for e in outgoing_edges.get(n.id, [])
                    if (e.relation_type.value if hasattr(e.relation_type, "value") else str(e.relation_type)) != RelationType.CONTAINS.value
                ]

                # Nếu là Storage entry, Cookie, Function, hoặc value node nhưng không ai đọc, không ai ghi
                if not non_contains_in and not non_contains_out:
                    to_prune_ids.add(n.id)

        # 5. Loại trừ các node nằm trong whitelist keep_node_ids
        to_prune_ids.difference_update(keep_node_ids)

        # 6. Xác định các edges cần xóa (bất kỳ edge nào nối với node bị xóa)
        to_prune_edge_ids = {
            e.id for e in edges
            if e.id and (e.source_id in to_prune_ids or e.target_id in to_prune_ids)
        }

        # 7. Xóa dữ liệu trong database
        if to_prune_ids:
            await self.graph_repo.delete_nodes(list(to_prune_ids))
        if to_prune_edge_ids:
            await self.graph_repo.delete_edges(list(to_prune_edge_ids))

        return {
            "session_id": session_id,
            "status": "compacted",
            "pruned_nodes_count": len(to_prune_ids),
            "pruned_edges_count": len(to_prune_edge_ids),
            "remaining_nodes_count": len(nodes) - len(to_prune_ids),
            "remaining_edges_count": len(edges) - len(to_prune_edge_ids),
            "pruned_node_ids": list(to_prune_ids),
        }
