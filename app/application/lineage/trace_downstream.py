from typing import Any
from collections import deque
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.ports.graph_repository import GraphRepositoryPort


class TraceDownstreamUseCase:
    """Use case tìm nơi một dữ liệu hoặc tham số được sử dụng xuôi dòng (Downstream Usage)."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)

    async def execute(
        self,
        session_id: str,
        source_node_id: str,
        max_depth: int = 10,
        max_nodes: int = 200,
        min_confidence: float = 0.8,
    ) -> dict[str, Any]:
        nodes = await self.graph_repo.get_nodes(session_id)
        edges = await self.graph_repo.get_edges(session_id)
        node_map = {n.id: n for n in nodes}

        # Resolve initial node
        start_node = node_map.get(source_node_id) or next((n for n in nodes if n.entity_id == source_node_id), None)
        if not start_node:
            return {"source": {"node_id": source_node_id}, "usages": [], "total_nodes_reached": 0}

        # Build adjacency list: node_id -> list of (edge, target_node_id)
        adj: dict[str, list[tuple[Any, str]]] = {}
        for e in edges:
            if e.confidence >= min_confidence:
                adj.setdefault(e.source_id, []).append((e, e.target_id))

        usages = []
        visited = set()
        queue = deque([(start_node.id, 0, [])])  # (curr_node_id, depth, path)
        visited.add(start_node.id)

        while queue and len(visited) <= max_nodes:
            curr_id, depth, path = queue.popleft()
            if depth >= max_depth:
                continue

            for edge, next_id in adj.get(curr_id, []):
                next_node = node_map.get(next_id)
                if not next_node:
                    continue

                new_path = path + [f"{edge.relation_type} -> {next_node.label}"]
                usage_type = "DIRECT_USAGE"
                if edge.relation_type in ("TRANSFORMS", "COMPUTES"):
                    usage_type = "TRANSFORMED_USAGE"
                elif edge.provenance_status == "inferred":
                    usage_type = "CANDIDATE_USAGE"

                usages.append({
                    "target_node_id": next_node.id,
                    "target_label": next_node.label,
                    "target_type": next_node.node_type,
                    "usage_type": usage_type,
                    "depth": depth + 1,
                    "relation": edge.relation_type,
                    "confidence": edge.confidence,
                    "path_summary": " -> ".join(new_path),
                })

                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, depth + 1, new_path))

        return {
            "source": {
                "node_id": start_node.id,
                "label": start_node.label,
                "node_type": start_node.node_type,
            },
            "usages": usages,
            "total_nodes_reached": len(visited),
            "truncated": len(visited) >= max_nodes,
        }
