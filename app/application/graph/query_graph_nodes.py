from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.ports.graph_repository import GraphRepositoryPort


class GetGraphNodeUseCase:
    """Use case lấy thông tin chi tiết một GraphNode kèm properties và evidence."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)

    async def execute(self, session_id: str, node_id: str, include_evidence: bool = True) -> dict[str, Any] | None:
        nodes = await self.graph_repo.get_nodes(session_id)
        target_node = next((n for n in nodes if n.id == node_id or n.entity_id == node_id), None)
        if not target_node:
            return None

        evidence_list = []
        if include_evidence:
            edges = await self.graph_repo.get_edges(session_id)
            for e in edges:
                if e.source_id == target_node.id or e.target_id == target_node.id:
                    for ev in e.evidence_list:
                        evidence_list.append(ev.model_dump())

        return {
            "node": target_node.model_dump(),
            "evidence": evidence_list,
        }


class GetGraphNeighborsUseCase:
    """Use case lấy danh sách các node liên kề (neighbors) 1-hop."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)

    async def execute(
        self,
        session_id: str,
        node_id: str,
        direction: str = "both",
        edge_types: list[str] | None = None,
        min_confidence: float = 0.8,
        limit: int = 100,
    ) -> dict[str, Any]:
        nodes = await self.graph_repo.get_nodes(session_id)
        node_map = {n.id: n for n in nodes}

        # Resolve node_id if passed as entity_id
        central_node = node_map.get(node_id)
        if not central_node:
            central_node = next((n for n in nodes if n.entity_id == node_id), None)
        if not central_node:
            return {"central_node_id": node_id, "neighbors": [], "total_count": 0}

        c_id = central_node.id
        edges = await self.graph_repo.get_edges(session_id)

        neighbors = []
        for e in edges:
            if e.confidence < min_confidence:
                continue
            if edge_types and e.relation_type not in edge_types:
                continue

            rel_info = {
                "relation_type": e.relation_type,
                "confidence": e.confidence,
                "provenance_status": e.provenance_status,
                "properties": e.properties,
            }

            if direction in ("out", "both") and e.source_id == c_id:
                target = node_map.get(e.target_id)
                if target:
                    neighbors.append({
                        "direction": "out",
                        "edge": rel_info,
                        "neighbor_node": target.model_dump(),
                    })

            if direction in ("in", "both") and e.target_id == c_id:
                source = node_map.get(e.source_id)
                if source:
                    neighbors.append({
                        "direction": "in",
                        "edge": rel_info,
                        "neighbor_node": source.model_dump(),
                    })

            if len(neighbors) >= limit:
                break

        return {
            "central_node_id": c_id,
            "central_node_label": central_node.label,
            "direction": direction,
            "neighbors": neighbors,
            "total_count": len(neighbors),
        }


class GetGraphStatisticsUseCase:
    """Use case tính toán các chỉ số thống kê chất lượng đồ thị."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)

    async def execute(
        self,
        session_id: str,
        include_edge_distribution: bool = True,
        include_orphans: bool = True,
    ) -> dict[str, Any]:
        nodes = await self.graph_repo.get_nodes(session_id)
        edges = await self.graph_repo.get_edges(session_id)

        connected_node_ids = set()
        edge_dist: dict[str, int] = {}
        inferred_edges_count = 0

        for e in edges:
            connected_node_ids.add(e.source_id)
            connected_node_ids.add(e.target_id)
            edge_dist[e.relation_type] = edge_dist.get(e.relation_type, 0) + 1
            if e.provenance_status == "inferred":
                inferred_edges_count += 1

        node_dist: dict[str, int] = {}
        orphan_count = 0
        for n in nodes:
            node_dist[n.node_type] = node_dist.get(n.node_type, 0) + 1
            if n.id not in connected_node_ids:
                orphan_count += 1

        inferred_ratio = round(inferred_edges_count / len(edges), 3) if edges else 0.0

        stats: dict[str, Any] = {
            "session_id": session_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "inferred_edge_count": inferred_edges_count,
            "inferred_edge_ratio": inferred_ratio,
            "node_distribution": node_dist,
            "projection_version": "graph-v1",
        }

        if include_edge_distribution:
            stats["edge_distribution"] = edge_dist
        if include_orphans:
            stats["orphan_nodes_count"] = orphan_count

        return stats
