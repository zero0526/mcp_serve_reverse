from typing import Any
from app.adapters.persistence.sqlite.connection import AsyncSessionLocal
from app.adapters.persistence.sqlite.graph_repository import SQLiteGraphRepository
from app.domain.graph.nodes import NodeType
from app.domain.graph.relations import RelationType
from app.ports.graph_repository import GraphRepositoryPort


class FindRequestDependenciesUseCase:
    """Use case tìm các phụ thuộc (Dependencies) của một HTTP Request."""

    def __init__(self, graph_repo: GraphRepositoryPort | None = None, session_factory=AsyncSessionLocal):
        self.graph_repo = graph_repo or SQLiteGraphRepository(session_factory)

    async def execute(
        self,
        session_id: str,
        request_id: str,
        include_storage: bool = True,
        include_executions: bool = True,
        max_depth: int = 10,
    ) -> dict[str, Any]:
        nodes = await self.graph_repo.get_nodes(session_id)
        edges = await self.graph_repo.get_edges(session_id)
        node_map = {n.id: n for n in nodes}

        req_node = next(
            (
                n
                for n in nodes
                if n.node_type == NodeType.HTTP_REQUEST
                and (n.id == request_id or n.entity_id == request_id or request_id in (n.entity_id or ""))
            ),
            None,
        )
        if not req_node:
            return {"request_id": request_id, "dependencies": []}

        dependencies = []

        # 1. Inbound edges to request
        for e in edges:
            if e.target_id == req_node.id:
                s_node = node_map.get(e.source_id)
                if not s_node:
                    continue

                if e.relation_type == RelationType.READS_FROM and include_storage:
                    dependencies.append({
                        "type": "STORAGE_DEPENDENCY",
                        "node_id": s_node.id,
                        "label": s_node.label,
                        "confidence": e.confidence,
                        "provenance": e.provenance_status,
                    })

                elif e.relation_type == RelationType.CALLS and include_executions:
                    dependencies.append({
                        "type": "FUNCTION_DISPATCHER",
                        "node_id": s_node.id,
                        "label": s_node.label,
                        "confidence": e.confidence,
                        "provenance": e.provenance_status,
                    })

                elif e.relation_type == RelationType.USED_IN:
                    dependencies.append({
                        "type": "VALUE_PARAMETER",
                        "node_id": s_node.id,
                        "label": s_node.label,
                        "confidence": e.confidence,
                        "provenance": e.provenance_status,
                    })

        # 2. Storage write back
        for e in edges:
            if e.source_id == req_node.id and e.relation_type == RelationType.STORES_IN and include_storage:
                t_node = node_map.get(e.target_id)
                if t_node:
                    dependencies.append({
                        "type": "STORAGE_MUTATION",
                        "node_id": t_node.id,
                        "label": t_node.label,
                        "confidence": e.confidence,
                        "provenance": e.provenance_status,
                    })

        return {
            "request_id": req_node.entity_id or req_node.id,
            "request_url": req_node.properties.get("url"),
            "dependencies": dependencies,
            "total_dependencies": len(dependencies),
        }
